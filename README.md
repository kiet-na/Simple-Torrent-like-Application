# Simple Torrent-Like Application

A Python-based BitTorrent-like peer-to-peer (P2P) file-sharing system supporting multi-directional data transfer. This project includes a tracker server, a seeder, and multiple leechers, all deployable using VirtualBox.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
  - [Running the Tracker](#running-the-tracker)
  - [Running the Seeder](#running-the-seeder)
  - [Running the Leechers](#running-the-leechers)


## Overview

The **Simple Torrent-Like Application (STA)** is designed to demonstrate the fundamental concepts of the BitTorrent protocol, including peer discovery, piece management, and data integrity verification. The application consists of:

- **Tracker Server (`simple_tracker.py`):** Manages peer registrations and facilitates peer discovery.
- **Seeder (`run_node.py` with seeder role):** Hosts complete files and shares them with leechers.
- **Leechers (`run_node.py` with leecher role):** Download and upload file pieces, participating in the P2P network.

## Features

- **Peer Discovery:** Connects to a tracker to find and communicate with peers.
- **Piece Management:** Splits files into pieces, downloads them from multiple peers, and verifies integrity using SHA-1 hashes.
- **Choking/Unchoking Mechanism:** Manages upload slots based on peer interest.
- **Rarest First Strategy:** Prioritizes downloading less common pieces to enhance distribution efficiency.
- **Command-Line Interface:** Provides commands to monitor status, peers, pieces, and speeds.
- **Deployment Flexibility:** Easily deployable using VirtualBox with multiple VMs acting as tracker, seeder, and leechers.

## Prerequisites

Ensure you have the following installed on your system:

- **Python 3.6 or higher**
- **VirtualBox** (for deploying multiple VMs)
- **Python Packages:**
  - `bencodepy`
  - `requests`

## Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/kiet-na/Simple-Torrent-like-Application.git
   cd Simple-Torrent-like-Application
2. **Install Python Packages**
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

3. **Prepare Torrent Files**
## Usage
1. **Running the tracker**

   ```bash
   python simple_tracker.py
3. **Running the seeder**
   ```bash
   python run_node.py path/to/seeder.torrent -p 6881 -o /path/to/download_directory --role seeder --verbose
5. **Running the leecher**
   ```bash
   python run_node.py path/to/leecher.torrent -p 6882 -o /path/to/download_directory --role leecher --verbose
