# 🔗 Hyperledger Supply Chain Tracking

A permissioned blockchain-based supply chain management system built with **Hyperledger Fabric**, **Go Chaincode**, and **Streamlit**. The system enables multiple organizations to securely track products, shipments, ownership transfers, and product lifecycle status across a shared distributed ledger.

## 📌 Overview

Traditional supply chains involve multiple independent organizations that maintain and exchange their own records, making it difficult to maintain a consistent and verifiable view of product movement.

This project implements a **multi-organization supply chain network** using Hyperledger Fabric, where manufacturers, distributors, and retailers interact with a shared permissioned ledger through smart-contract-controlled transactions.

The system consists of:

- **Org1MSP — Manufacturer**
- **Org2MSP — Distributor**
- **Org3MSP — Retailer**

A **Streamlit dashboard** provides an interactive interface for performing blockchain transactions and querying product and shipment information.

---

## 🏗️ System Architecture

```text
                    ┌─────────────────────────┐
                    │   Streamlit Dashboard   │
                    │       Python            │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │       Windows / WSL2     │
                    │     Fabric CLI Bridge    │
                    └────────────┬────────────┘
                                 │
                                 ▼
                 ┌─────────────────────────────────┐
                 │       Hyperledger Fabric        │
                 │                                 │
                 │        supplychannel            │
                 │                                 │
                 │  ┌─────────┐ ┌─────────┐       │
                 │  │  Org1   │ │  Org2   │       │
                 │  │Manufacturer│Distributor│     │
                 │  └─────────┘ └─────────┘       │
                 │        ┌─────────┐              │
                 │        │  Org3   │              │
                 │        │ Retailer│              │
                 │        └─────────┘              │
                 │                                 │
                 │          Orderer                │
                 └─────────────────────────────────┘
                                 │
                                 ▼
                       Distributed Ledger
