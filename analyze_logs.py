"""
Log Analysis Tool for HFT FPGA Trading System
Analyzes MongoDB logs for packets, decisions, and trades
"""
from pymongo import MongoClient
from datetime import datetime, timedelta
import sys


def get_db():
    """Connect to MongoDB"""
    try:
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        return client['hft_logs']
    except Exception as e:
        print(f"[ERROR] MongoDB connection failed: {e}")
        return None


def format_section(title):
    """Format section header"""
    return f"\n{'='*70}\n  {title}\n{'='*70}\n"


def print_basic_statistics(db):
    """Print basic collection statistics"""
    print(format_section("Basic Statistics"))

    packet_count = db['packets'].count_documents({})
    decision_count = db['decisions'].count_documents({})
    trade_count = db['trades'].count_documents({})

    print(f"Total Packets:   {packet_count}")
    print(f"Total Decisions: {decision_count}")
    print(f"Total Trades:    {trade_count}")


def print_decision_breakdown(db):
    """Print decision action breakdown"""
    print(format_section("Decision Breakdown"))

    buy_count = db['decisions'].count_documents({"action": "BUY"})
    sell_count = db['decisions'].count_documents({"action": "SELL"})
    hold_count = db['decisions'].count_documents({"action": "HOLD"})
    parse_errors = db['decisions'].count_documents({"valid": False})

    print(f"BUY:           {buy_count}")
    print(f"SELL:          {sell_count}")
    print(f"HOLD:          {hold_count}")
    print(f"Parse Errors:  {parse_errors}")

    total = buy_count + sell_count + hold_count
    if total > 0:
        print(f"\nBUY %:         {buy_count/total*100:.1f}%")
        print(f"SELL %:        {sell_count/total*100:.1f}%")
        print(f"HOLD %:        {hold_count/total*100:.1f}%")


def print_trade_stats(db):
    """Print trade statistics"""
    print(format_section("Trade Statistics"))

    successful_trades = db['trades'].count_documents({"success": True})
    failed_trades = db['trades'].count_documents({"success": False})
    total_trades = successful_trades + failed_trades

    print(f"Successful:     {successful_trades}")
    print(f"Failed:         {failed_trades}")
    print(f"Total:          {total_trades}")

    if total_trades > 0:
        success_rate = successful_trades / total_trades * 100
        print(f"Success Rate:   {success_rate:.1f}%")

    # Calculate volume
    if successful_trades > 0:
        total_volume = db['trades'].aggregate([
            {"$group": {"_id": None, "total_qty": {"$sum": "$quantity"}}}
        ])
        for doc in total_volume:
            print(f"Total Volume:   {doc['total_qty']} shares")

        # Average trade size
        avg_size = db['trades'].aggregate([
            {"$group": {"_id": None, "avg_qty": {"$avg": "$quantity"}}}
        ])
        for doc in avg_size:
            print(f"Avg Trade Size: {doc['avg_qty']:.1f} shares")


def print_fpga_latency(db):
    """Print average FPGA latency"""
    print(format_section("FPGA Latency Analysis"))

    # Get all decisions with valid timestamps
    pipeline = [
        {"$match": {"valid": True}},
        {"$group": {
            "_id": None,
            "avg_fpga_ts": {"$avg": "$fpga_timestamp"},
            "count": {"$sum": 1}
        }}
    ]

    result = list(db['decisions'].aggregate(pipeline))
    if result and result[0]['count'] > 0:
        avg_ts = result[0]['avg_fpga_ts']
        count = result[0]['count']
        print(f"Valid Decisions: {count}")
        print(f"Avg FPGA Time:   {int(avg_ts)} (Unix timestamp)")
    else:
        print("No valid FPGA timestamps found")


def print_ticker_breakdown(db):
    """Print breakdown by ticker"""
    print(format_section("Ticker Breakdown"))

    # Aggregate by ticker
    pipeline = [
        {"$group": {
            "_id": "$ticker",
            "packet_count": {"$sum": 1},
            "buy_actions": {
                "$sum": {"$cond": [{"$eq": ["$action", "BUY"]}, 1, 0]}
            },
            "sell_actions": {
                "$sum": {"$cond": [{"$eq": ["$action", "SELL"]}, 1, 0]}
            },
            "hold_actions": {
                "$sum": {"$cond": [{"$eq": ["$action", "HOLD"]}, 1, 0]}
            }
        }},
        {"$sort": {"_id": 1}}
    ]

    results = list(db['decisions'].aggregate(pipeline))
    if results:
        print(f"{'Ticker':<10} {'Packets':<10} {'BUY':<8} {'SELL':<8} {'HOLD':<8}")
        print("-" * 50)
        for doc in results:
            ticker = doc['_id'] or 'UNKNOWN'
            packets = doc['packet_count']
            buys = doc['buy_actions']
            sells = doc['sell_actions']
            holds = doc['hold_actions']
            print(f"{ticker:<10} {packets:<10} {buys:<8} {sells:<8} {holds:<8}")
    else:
        print("No ticker data found")


def print_recent_entries(db, limit=3):
    """Print recent log entries from each collection"""
    print(format_section("Recent Entries"))

    # Recent packets
    print("--- Recent Packets ---")
    packets = list(db['packets'].find().sort('timestamp', -1).limit(limit))
    if packets:
        for p in packets:
            print(f"  {p['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} | {p['ticker']} | "
                  f"Ask=${p['ask_price']:.2f} Bid=${p['bid_price']:.2f} | "
                  f"Pos={p['position']:+d}")
    else:
        print("  (No packets found)")

    # Recent decisions
    print("\n--- Recent Decisions ---")
    decisions = list(db['decisions'].find().sort('timestamp', -1).limit(limit))
    if decisions:
        for d in decisions:
            status = "✓" if d['valid'] else "✗"
            action = d['action']
            qty = d['quantity'] or "N/A"
            print(f"  {d['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} | {status} | "
                  f"{action} {qty} | {d.get('order_type', 'N/A')}")
    else:
        print("  (No decisions found)")

    # Recent trades
    print("\n--- Recent Trades ---")
    trades = list(db['trades'].find().sort('timestamp', -1).limit(limit))
    if trades:
        for t in trades:
            print(f"  {t['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} | {t['ticker']} | "
                  f"{t['action']} {t['quantity']} @ ${t['price']:.2f} | "
                  f"Pos={t['new_position']:+d}")
    else:
        print("  (No trades found)")


def main():
    """Main analysis routine"""
    db = get_db()
    if db is None:
        sys.exit(1)

    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  HFT FPGA Trading System - Log Analysis".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "=" * 68 + "╝")

    try:
        print_basic_statistics(db)
        print_decision_breakdown(db)
        print_trade_stats(db)
        print_fpga_latency(db)
        print_ticker_breakdown(db)
        print_recent_entries(db)

        print(format_section("Analysis Complete"))
        print("MongoDB connection closed.\n")

    except Exception as e:
        print(f"\n[ERROR] Analysis failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
