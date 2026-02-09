"""
MongoDB Logger for HFT FPGA Trading System
Handles logging of packets, decisions, and trades to MongoDB
"""
from datetime import datetime
from pymongo import MongoClient

# Initialize MongoDB client (lazy connection on first operation)
_client = None
_db = None


def _get_db():
    """Get MongoDB database connection, initializing if needed"""
    global _client, _db
    if _client is None:
        try:
            _client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
            _db = _client['hft_logs']
            # Test connection
            _client.admin.command('ping')
        except Exception as e:
            print(f"[MONGO] Connection error: {e}")
            _db = None
    return _db


def log_packet(ticker, ask_price, bid_price, position, packet_bytes):
    """
    Log market data packet sent to FPGA

    Args:
        ticker (str): Stock ticker
        ask_price (float): Ask price
        bid_price (float): Bid price
        position (int): Current position
        packet_bytes (bytes): Raw packet data
    """
    try:
        db = _get_db()
        if db is None:
            return

        doc = {
            'timestamp': datetime.now(),
            'ticker': ticker,
            'ask_price': ask_price,
            'bid_price': bid_price,
            'position': position,
            'raw_hex': packet_bytes.hex(),
            'packet_size': len(packet_bytes)
        }

        db['packets'].insert_one(doc)
        print(f"[MONGO] Logged packet for {ticker}")
    except Exception as e:
        print(f"[MONGO] Error logging packet: {e}")


def log_decision(decision_dict, raw_response):
    """
    Log FPGA trading decision

    Args:
        decision_dict (dict or None): Decoded decision from FPGA
        raw_response (bytes): Raw response bytes from FPGA
    """
    try:
        db = _get_db()
        if db is None:
            return

        valid = decision_dict is not None

        doc = {
            'timestamp': datetime.now(),
            'ticker': decision_dict.get('ticker') if decision_dict else None,
            'action': decision_dict.get('action') if decision_dict else 'PARSE_ERROR',
            'quantity': decision_dict.get('quantity') if decision_dict else None,
            'order_type': decision_dict.get('order_type') if decision_dict else None,
            'limit_price': decision_dict.get('limit_price') if decision_dict else None,
            'fpga_timestamp': decision_dict.get('timestamp') if decision_dict else None,
            'raw_hex': raw_response.hex(),
            'valid': valid
        }

        db['decisions'].insert_one(doc)
        status = "OK" if valid else "PARSE_ERROR"
        print(f"[MONGO] Logged decision: {status}")
    except Exception as e:
        print(f"[MONGO] Error logging decision: {e}")


def log_trade(ticker, action, quantity, price, new_position):
    """
    Log executed trade

    Args:
        ticker (str): Stock ticker
        action (str): "BUY" or "SELL"
        quantity (int): Number of shares
        price (float): Execution price (ask for BUY, bid for SELL)
        new_position (int): Updated position after trade
    """
    try:
        db = _get_db()
        if db is None:
            return

        doc = {
            'timestamp': datetime.now(),
            'ticker': ticker,
            'action': action,
            'quantity': quantity,
            'price': price,
            'new_position': new_position,
            'success': True  # Simulated trades always succeed
        }

        db['trades'].insert_one(doc)
        print(f"[MONGO] Logged trade: {action} {quantity} shares of {ticker} at ${price:.2f}")
    except Exception as e:
        print(f"[MONGO] Error logging trade: {e}")


def close_connection():
    """Close MongoDB connection"""
    global _client
    if _client:
        try:
            _client.close()
            print("[MONGO] Connection closed")
        except Exception as e:
            print(f"[MONGO] Error closing connection: {e}")
        finally:
            _client = None
