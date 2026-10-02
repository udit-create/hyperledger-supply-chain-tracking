"""
Supply Chain Blockchain Dashboard
Streamlit (Windows/PyCharm) <-> WSL2 Ubuntu <-> Hyperledger Fabric test-network

This app shells out to `wsl.exe` to invoke the Fabric peer CLI binary directly
(absolute Linux path), constructing a clean environment so the Windows PATH
does not leak into the WSL bash session.
"""

import json
import shlex
import subprocess
import streamlit as st

# ==================================================
# STATIC CONFIGURATION (DO NOT CHANGE)
# ==================================================

WSL_DISTRIBUTION = "Ubuntu"

FABRIC_SAMPLES_DIR = "/home/uditb/supply-chain-blockchain/fabric-samples"
TEST_NETWORK_DIR = f"{FABRIC_SAMPLES_DIR}/test-network"
PEER_BINARY = f"{FABRIC_SAMPLES_DIR}/bin/peer"
FABRIC_CFG_PATH = f"{FABRIC_SAMPLES_DIR}/config"

CHANNEL_NAME = "supplychannel"
CHAINCODE_NAME = "supplychain"

ORDERER_ADDRESS = "localhost:7050"
ORDERER_TLS_HOSTNAME_OVERRIDE = "orderer.example.com"
ORDERER_CA = (
    f"{TEST_NETWORK_DIR}/organizations/ordererOrganizations/example.com/"
    f"orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem"
)

ORG_CONFIG = {
    "Org1MSP": {
        "label": "Org1MSP (Manufacturer)",
        "peer_address": "localhost:7051",
        "msp_path": (
            f"{TEST_NETWORK_DIR}/organizations/peerOrganizations/org1.example.com/"
            f"users/Admin@org1.example.com/msp"
        ),
        "tls_ca": (
            f"{TEST_NETWORK_DIR}/organizations/peerOrganizations/org1.example.com/"
            f"peers/peer0.org1.example.com/tls/ca.crt"
        ),
    },
    "Org2MSP": {
        "label": "Org2MSP (Distributor)",
        "peer_address": "localhost:9051",
        "msp_path": (
            f"{TEST_NETWORK_DIR}/organizations/peerOrganizations/org2.example.com/"
            f"users/Admin@org2.example.com/msp"
        ),
        "tls_ca": (
            f"{TEST_NETWORK_DIR}/organizations/peerOrganizations/org2.example.com/"
            f"peers/peer0.org2.example.com/tls/ca.crt"
        ),
    },
    "Org3MSP": {
        "label": "Org3MSP (Retailer)",
        "peer_address": "localhost:11051",
        "msp_path": (
            f"{TEST_NETWORK_DIR}/organizations/peerOrganizations/org3.example.com/"
            f"users/Admin@org3.example.com/msp"
        ),
        "tls_ca": (
            f"{TEST_NETWORK_DIR}/organizations/peerOrganizations/org3.example.com/"
            f"peers/peer0.org3.example.com/tls/ca.crt"
        ),
    },
}

ALL_ORGS = ["Org1MSP", "Org2MSP", "Org3MSP"]

STATUS_OPTIONS = [
    "CREATED",
    "IN_TRANSIT",
    "RECEIVED",
    "DELIVERED",
    "DAMAGED",
    "CANCELLED",
]

FABRIC_TIMEOUT_SECONDS = 60


# ==================================================
# HELPER FUNCTIONS
# ==================================================

def build_environment(org_msp_id: str) -> dict:
    """
    Build the CORE_PEER_* environment variable exports for the given
    organization, to be prefixed onto the bash script executed inside WSL.
    Uses shlex.quote() on every value that is interpolated into the shell.
    """
    org = ORG_CONFIG[org_msp_id]

    exports = {
        "CORE_PEER_TLS_ENABLED": "true",
        "CORE_PEER_LOCALMSPID": org_msp_id,
        "CORE_PEER_MSPCONFIGPATH": org["msp_path"],
        "CORE_PEER_ADDRESS": org["peer_address"],
        "CORE_PEER_TLS_ROOTCERT_FILE": org["tls_ca"],
        "FABRIC_CFG_PATH": FABRIC_CFG_PATH,
    }
    return exports


def _exports_to_bash(exports: dict) -> str:
    """Turn an environment dict into a sequence of safely-quoted bash export statements."""
    lines = []
    for key, value in exports.items():
        lines.append(f"export {key}={shlex.quote(value)}")
    return "\n".join(lines)


def run_fabric(bash_script: str) -> dict:
    """
    Execute a bash script inside WSL Ubuntu via wsl.exe, using a clean
    environment that does NOT inherit the normal Windows PATH (to avoid the
    Windows PATH leaking into WSL and corrupting bash exports).

    Returns a dict:
        {
            "success": bool,
            "returncode": int or None,
            "stdout": str,
            "stderr": str,
            "error": str or None,   # populated for exceptions (timeout, wsl missing, etc.)
        }
    """
    clean_env = {
        "SystemRoot": r"C:\Windows",
        "PATH": r"C:\Windows\System32;C:\Windows",
    }

    try:
        completed = subprocess.run(
            [
                "wsl.exe",
                "--distribution",
                WSL_DISTRIBUTION,
                "--",
                "bash",
                "-c",
                bash_script,
            ],
            env=clean_env,
            capture_output=True,
            text=True,
            timeout=FABRIC_TIMEOUT_SECONDS,
        )
        return {
            "success": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "error": None,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "error": (
                "wsl.exe was not found. Make sure WSL2 is installed and "
                "accessible on the Windows PATH used to launch this app."
            ),
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "error": (
                f"The Fabric command timed out after {FABRIC_TIMEOUT_SECONDS} "
                "seconds. Check that the Fabric test-network and Docker "
                "containers are running inside WSL."
            ),
        }
    except Exception as exc:  # noqa: BLE001 - surface any unexpected failure to the user
        return {
            "success": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "error": f"Unexpected error while invoking WSL: {exc}",
        }


def make_query(org_msp_id: str, function_name: str, args: list) -> dict:
    """
    Build and execute a `peer chaincode query` command using the selected
    organization's identity, against the selected organization's own peer.
    """
    exports = build_environment(org_msp_id)
    export_block = _exports_to_bash(exports)

    chaincode_payload = json.dumps({"function": function_name, "Args": args})

    query_cmd = (
        f"{shlex.quote(PEER_BINARY)} chaincode query "
        f"-C {shlex.quote(CHANNEL_NAME)} "
        f"-n {shlex.quote(CHAINCODE_NAME)} "
        f"-c {shlex.quote(chaincode_payload)}"
    )

    bash_script = f"{export_block}\n{query_cmd}"

    result = run_fabric(bash_script)
    result["command"] = query_cmd
    return result


def make_invoke(org_msp_id: str, function_name: str, args: list) -> dict:
    """
    Build and execute a `peer chaincode invoke` command using the selected
    organization's identity as the caller, but endorsed by ALL THREE
    organizations' peers, per the committed endorsement policy:

        AND('Org1MSP.peer', 'Org2MSP.peer', 'Org3MSP.peer')
    """
    exports = build_environment(org_msp_id)
    export_block = _exports_to_bash(exports)

    chaincode_payload = json.dumps({"function": function_name, "Args": args})

    peer_address_flags = []
    for org_id in ALL_ORGS:
        org = ORG_CONFIG[org_id]
        peer_address_flags.append(f"--peerAddresses {shlex.quote(org['peer_address'])}")
        peer_address_flags.append(f"--tlsRootCertFiles {shlex.quote(org['tls_ca'])}")
    peer_address_block = " ".join(peer_address_flags)

    invoke_cmd = (
        f"{shlex.quote(PEER_BINARY)} chaincode invoke "
        f"-o {shlex.quote(ORDERER_ADDRESS)} "
        f"--ordererTLSHostnameOverride {shlex.quote(ORDERER_TLS_HOSTNAME_OVERRIDE)} "
        f"--tls "
        f"--cafile {shlex.quote(ORDERER_CA)} "
        f"-C {shlex.quote(CHANNEL_NAME)} "
        f"-n {shlex.quote(CHAINCODE_NAME)} "
        f"{peer_address_block} "
        f"-c {shlex.quote(chaincode_payload)}"
    )

    bash_script = f"{export_block}\n{invoke_cmd}"

    result = run_fabric(bash_script)
    result["command"] = invoke_cmd
    return result


def _try_parse_json(text: str):
    """Attempt to parse text as JSON; return the parsed object, or None if it fails."""
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def display_result(result: dict, success_message: str = "Transaction submitted successfully."):
    """
    Render a Fabric command result dict (from run_fabric / make_query / make_invoke)
    in Streamlit. Shows the actual Fabric stdout/stderr on failure so the user can debug.
    """
    if result.get("error"):
        st.error(result["error"])
        return

    stdout = result.get("stdout", "") or ""
    stderr = result.get("stderr", "") or ""

    if result.get("success"):
        st.success(success_message)

        # Fabric invoke responses often print status/result info to stderr even
        # on success (peer CLI logs go to stderr), and query results usually go
        # to stdout. Check both for JSON content to display nicely.
        combined_output = stdout if stdout.strip() else stderr

        parsed = _try_parse_json(combined_output)
        if parsed is not None:
            st.json(parsed)
        elif combined_output.strip():
            st.code(combined_output, language="text")

        with st.expander("Raw command output"):
            st.text("STDOUT:")
            st.code(stdout if stdout.strip() else "(empty)", language="text")
            st.text("STDERR:")
            st.code(stderr if stderr.strip() else "(empty)", language="text")
    else:
        st.error(
            f"Fabric command failed (exit code: {result.get('returncode')}). "
            "See details below."
        )
        st.text("STDOUT:")
        st.code(stdout if stdout.strip() else "(empty)", language="text")
        st.text("STDERR:")
        st.code(stderr if stderr.strip() else "(empty)", language="text")

    if "command" in result:
        with st.expander("Command executed"):
            st.code(result["command"], language="bash")


# ==================================================
# PAGE CONFIG
# ==================================================

st.set_page_config(
    page_title="Supply Chain Blockchain Dashboard",
    page_icon="\U0001F4E6",
    layout="wide",
)

st.title("Supply Chain Blockchain Dashboard")
st.caption("Hyperledger Fabric \u2022 Manufacturer \u2192 Distributor \u2192 Retailer")


# ==================================================
# SIDEBAR
# ==================================================

with st.sidebar:
    st.header("Current Organization")

    selected_org = st.selectbox(
        "Select organization",
        options=ALL_ORGS,
        format_func=lambda org_id: ORG_CONFIG[org_id]["label"],
        key="selected_org",
    )

    st.markdown(f"**Role:** {ORG_CONFIG[selected_org]['label'].split('(')[-1].rstrip(')')}")

    st.divider()

    st.markdown(f"**Channel:**  \n`{CHANNEL_NAME}`")
    st.markdown(f"**Chaincode:**  \n`{CHAINCODE_NAME}`")
    st.markdown(f"**Peer address:**  \n`{ORG_CONFIG[selected_org]['peer_address']}`")


# ==================================================
# NETWORK STATUS
# ==================================================

st.subheader("Network Status")

status_col1, status_col2, status_col3, status_col4 = st.columns(4)

with status_col1:
    st.metric("Channel", CHANNEL_NAME)

with status_col2:
    st.metric("Chaincode", CHAINCODE_NAME)

with status_col3:
    st.metric("Organization", selected_org)

with status_col4:
    st.metric("Peer", ORG_CONFIG[selected_org]["peer_address"])

st.divider()


# ==================================================
# TABS
# ==================================================

(
    tab_create_product,
    tab_create_shipment,
    tab_transfer_product,
    tab_receive_product,
    tab_get_product,
    tab_all_products,
    tab_get_shipment,
    tab_update_status,
) = st.tabs(
    [
        "Create Product",
        "Create Shipment",
        "Transfer Product",
        "Receive Product",
        "Get Product",
        "All Products",
        "Get Shipment",
        "Update Status",
    ]
)


# --------------------------------------------------
# TAB 1: CREATE PRODUCT
# --------------------------------------------------

with tab_create_product:
    st.subheader("Create Product")
    st.caption("Only Org1MSP (Manufacturer) may create products.")

    cp_product_id = st.text_input("Product ID", key="create_product_id")
    cp_name = st.text_input("Product Name", key="create_product_name")
    cp_category = st.text_input("Category", key="create_product_category")
    cp_quantity = st.text_input("Quantity", key="create_product_quantity")

    if st.button("Create Product", key="create_product_button"):
        if selected_org != "Org1MSP":
            st.error("CreateProduct must be executed by Org1MSP.")
        elif not cp_product_id or not cp_name or not cp_category or not cp_quantity:
            st.warning("Please fill in all fields before submitting.")
        else:
            result = make_invoke(
                selected_org,
                "CreateProduct",
                [cp_product_id, cp_name, cp_category, cp_quantity],
            )
            display_result(result, success_message=f"Product '{cp_product_id}' created.")


# --------------------------------------------------
# TAB 2: CREATE SHIPMENT
# --------------------------------------------------

with tab_create_shipment:
    st.subheader("Create Shipment")
    st.caption(
        "The currently selected organization is used as the caller / current owner. "
        "Note: CreateShipment does NOT automatically reduce the product quantity."
    )

    cs_shipment_id = st.text_input("Shipment ID", key="create_shipment_id")
    cs_product_id = st.text_input("Product ID", key="create_shipment_product_id")
    cs_destination = st.selectbox(
        "Destination",
        options=["Org2MSP", "Org3MSP"],
        key="create_shipment_destination",
    )
    cs_quantity = st.text_input("Quantity", key="create_shipment_quantity")

    if st.button("Create Shipment", key="create_shipment_button"):
        if not cs_shipment_id or not cs_product_id or not cs_quantity:
            st.warning("Please fill in all fields before submitting.")
        else:
            result = make_invoke(
                selected_org,
                "CreateShipment",
                [cs_shipment_id, cs_product_id, cs_destination, cs_quantity],
            )
            display_result(result, success_message=f"Shipment '{cs_shipment_id}' created.")


# --------------------------------------------------
# TAB 3: TRANSFER PRODUCT
# --------------------------------------------------

with tab_transfer_product:
    st.subheader("Transfer Product")
    st.caption("Caller must be the current owner. New owner can only be Org2MSP or Org3MSP.")

    tp_product_id = st.text_input("Product ID", key="transfer_product_id")
    tp_new_owner = st.selectbox(
        "New Owner",
        options=["Org2MSP", "Org3MSP"],
        key="transfer_product_new_owner",
    )

    if st.button("Transfer Product", key="transfer_product_button"):
        if not tp_product_id:
            st.warning("Please enter a Product ID.")
        elif selected_org == tp_new_owner:
            st.warning(
                f"'{selected_org}' cannot transfer the product to itself. "
                "Please select a different new owner."
            )
        else:
            result = make_invoke(
                selected_org,
                "TransferProduct",
                [tp_product_id, tp_new_owner],
            )
            display_result(
                result,
                success_message=f"Product '{tp_product_id}' transferred to {tp_new_owner}.",
            )


# --------------------------------------------------
# TAB 4: RECEIVE PRODUCT
# --------------------------------------------------

with tab_receive_product:
    st.subheader("Receive Product")
    st.caption("Caller must be the current owner, and the product must currently be IN_TRANSIT.")

    rp_product_id = st.text_input("Product ID", key="receive_product_id")

    if st.button("Receive Product", key="receive_product_button"):
        if not rp_product_id:
            st.warning("Please enter a Product ID.")
        else:
            result = make_invoke(
                selected_org,
                "ReceiveProduct",
                [rp_product_id],
            )
            display_result(result, success_message=f"Product '{rp_product_id}' received.")


# --------------------------------------------------
# TAB 5: GET PRODUCT
# --------------------------------------------------

with tab_get_product:
    st.subheader("Get Product")

    gp_product_id = st.text_input("Product ID", key="get_product_id")

    if st.button("Get Product", key="get_product_button"):
        if not gp_product_id:
            st.warning("Please enter a Product ID.")
        else:
            result = make_query(
                selected_org,
                "GetProduct",
                [gp_product_id],
            )
            display_result(result, success_message=f"Product '{gp_product_id}' retrieved.")


# --------------------------------------------------
# TAB 6: ALL PRODUCTS
# --------------------------------------------------

with tab_all_products:
    st.subheader("All Products")

    if st.button("Get All Products", key="get_all_products_button"):
        result = make_query(
            selected_org,
            "GetAllProducts",
            [],
        )

        if result.get("error"):
            st.error(result["error"])
        elif result.get("success"):
            st.success("Products retrieved successfully.")
            stdout = result.get("stdout", "") or ""
            stderr = result.get("stderr", "") or ""
            combined_output = stdout if stdout.strip() else stderr
            parsed = _try_parse_json(combined_output)

            if isinstance(parsed, list) and parsed:
                st.dataframe(parsed, use_container_width=True)
                with st.expander("Raw JSON"):
                    st.json(parsed)
            elif parsed is not None:
                st.json(parsed)
            elif combined_output.strip():
                st.code(combined_output, language="text")
            else:
                st.info("No products were returned by the ledger.")

            with st.expander("Raw command output"):
                st.text("STDOUT:")
                st.code(stdout if stdout.strip() else "(empty)", language="text")
                st.text("STDERR:")
                st.code(stderr if stderr.strip() else "(empty)", language="text")
        else:
            st.error(
                f"Fabric command failed (exit code: {result.get('returncode')}). "
                "See details below."
            )
            st.text("STDOUT:")
            st.code(result.get("stdout", "") or "(empty)", language="text")
            st.text("STDERR:")
            st.code(result.get("stderr", "") or "(empty)", language="text")

        if "command" in result:
            with st.expander("Command executed"):
                st.code(result["command"], language="bash")


# --------------------------------------------------
# TAB 7: GET SHIPMENT
# --------------------------------------------------

with tab_get_shipment:
    st.subheader("Get Shipment")

    gs_shipment_id = st.text_input("Shipment ID", key="get_shipment_id")

    if st.button("Get Shipment", key="get_shipment_button"):
        if not gs_shipment_id:
            st.warning("Please enter a Shipment ID.")
        else:
            result = make_query(
                selected_org,
                "GetShipment",
                [gs_shipment_id],
            )
            display_result(result, success_message=f"Shipment '{gs_shipment_id}' retrieved.")


# --------------------------------------------------
# TAB 8: UPDATE STATUS
# --------------------------------------------------

with tab_update_status:
    st.subheader("Update Status")
    st.caption("Caller must be the current owner.")

    us_product_id = st.text_input("Product ID", key="update_status_product_id")
    us_status = st.selectbox(
        "Status",
        options=STATUS_OPTIONS,
        key="update_status_value",
    )

    if st.button("Update Status", key="update_status_button"):
        if not us_product_id:
            st.warning("Please enter a Product ID.")
        else:
            result = make_invoke(
                selected_org,
                "UpdateProductStatus",
                [us_product_id, us_status],
            )
            display_result(
                result,
                success_message=f"Product '{us_product_id}' status updated to {us_status}.",
            )