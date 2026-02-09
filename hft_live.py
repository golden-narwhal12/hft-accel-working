#!/usr/bin/env python3
"""
FPGA HFT System with Live Market Data
"""
import serial
import time
import yfinance as yf
from datetime import datetime
from packet_protocol import encode_market_data, decode_trade_decision
from mongo_logger import log_packet, log_decision, log_trade, close_connection

class FPGATrader:
    def __init__(self, port='/dev/ttyUSB1', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.position = 0
        
    def connect(self):
        """Connect to FPGA"""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=2.0)
            print(f"[✓] Connected to FPGA on {self.port}")
            time.sleep(1)
            return True
        except Exception as e:
            print(f"[✗] Connection failed: {e}")
            return False
    
    def get_quote(self, ticker):
        """Fetch current market data"""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Get  bid/ask prices
            bid = info.get('bid', None)
            ask = info.get('ask', None)
            
            # Fallback to regular market price if bid/ask unavailable
            if bid is None or ask is None:
                current = info.get('currentPrice') or info.get('regularMarketPrice')
                if current is None:
                    return None
                return {
                    'ask': current,
                    'bid': current,
                    'last': current
                }
            
            return {
                'ask': ask,
                'bid': bid,
                'last': (ask + bid) / 2
            }
        except Exception as e:
            print(f"[!] Error: {e}")
            return None
    
    def send_and_receive(self, ticker, ask, bid):
        """Send market data and get FPGA decision"""
        packet = encode_market_data(
            ticker=ticker,
            ask_price=ask,
            bid_price=bid,
            position=self.position,
            timestamp=int(time.time())
        )

        self.ser.write(packet)
        log_packet(ticker, ask, bid, self.position, packet)
        time.sleep(0.2)

        if self.ser.in_waiting >= 16:
            response = self.ser.read(16)
            # Debug: Log raw FPGA response
            print(f"\n[DEBUG] Raw FPGA response: {' '.join(f'{b:02x}' for b in response)}")

            decision = decode_trade_decision(response)
            log_decision(decision, response)
            if decision:
                # Debug: Log decoded fields
                print(f"[DEBUG] Decoded - Action: {decision['action']}, "
                      f"Qty: {decision['quantity']}, OrderType: {decision['order_type']}")
                # Debug: Show spread calculation
                spread_cents = round((bid - ask) * 100)
                print(f"[DEBUG] Market - Ask: ${ask:.2f}, Bid: ${bid:.2f}, Spread: {spread_cents:+d} cents")
            return decision
        return None
    
    def run(self, ticker, duration=60):
        """Run trading loop"""
        print(f"\n{'='*70}")
        print(f"  FPGA HFT System - Live Trading {ticker}")
        print(f"  Duration: {duration} seconds")
        print(f"  Fetching data every 3 seconds...")
        print(f"{'='*70}\n")
        
        start_time = time.time()
        iteration = 0
        
        try:
            while time.time() - start_time < duration:
                iteration += 1
                
                # Fetch market data
                print(f"[{iteration}] Fetching {ticker} data...", end=" ", flush=True)
                quote = self.get_quote(ticker)
                
                if not quote:
                    print("FAILED - retrying...")
                    time.sleep(0.5)
                    continue
                
                ask = quote['ask']
                bid = quote['bid']
                mid = (ask + bid) / 2
                spread_cents = round((bid - ask) * 100)
                # Arbitrage only when bid > ask (positive spread >= 3¢)
                arbitrage_flag = "🚨 ARBITRAGE!" if spread_cents >= 3 else ""

                print(f"Ask=${ask:.2f} Bid=${bid:.2f} Spread={spread_cents:+d}¢ {arbitrage_flag} "
                      f"Pos={self.position:+3d}", end=" ")

                # Send to FPGA and get decision
                decision = self.send_and_receive(ticker, ask, bid)
                
                if decision:
                    action = decision['action']
                    qty = decision['quantity']

                    if action == 'BUY':
                        print(f"→ BUY {qty} shares ↗")
                        self.position += qty
                        log_trade(ticker, 'BUY', qty, ask, self.position)
                    elif action == 'SELL':
                        print(f"→ SELL {qty} shares ↘")
                        self.position -= qty
                        log_trade(ticker, 'SELL', qty, bid, self.position)
                    else:
                        print(f"→ HOLD ─")
                else:
                    print(f"→ NO RESPONSE")
                
                time.sleep(0.5)  # INTERVAL
                
        except KeyboardInterrupt:
            print(f"\n\n[!] Stopped by user")
        
        print(f"\n{'='*70}")
        print(f"Final Position: {self.position:+d} shares")
        print(f"{'='*70}\n")
    
    def close(self):
        if self.ser:
            self.ser.close()
        close_connection()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 hft_live.py <TICKER> [duration_seconds]")
        print("Example: python3 hft_live.py AAPL 30")
        sys.exit(1)
    
    ticker = sys.argv[1].upper()
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    
    trader = FPGATrader()
    
    if trader.connect():
        try:
            trader.run(ticker, duration)
        finally:
            trader.close()
    else:
        sys.exit(1)
