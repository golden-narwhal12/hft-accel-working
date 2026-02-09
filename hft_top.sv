`timescale 1ns/1ps

//============================================================================
// UART RX
//============================================================================
module uart_rx #(
    parameter CLK_FREQ = 100_000_000,
    parameter BAUD_RATE = 115200
)(
    input  logic clk,
    input  logic rst,
    input  logic rx,
    output logic [7:0] data,
    output logic valid
);
    localparam CYCLES_PER_BIT = CLK_FREQ / BAUD_RATE;

    typedef enum logic [2:0] {IDLE, START, DATA_BITS, STOP} state_t;
    state_t state = IDLE;

    logic [15:0] clk_count = 0;
    logic [2:0] bit_index = 0;
    logic [7:0] rx_byte = 0;

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            valid <= 0;
        end else begin
            valid <= 0;

            case (state)
                IDLE: begin
                    if (rx == 0) begin
                        state <= START;
                        clk_count <= 0;
                    end
                end

                START: begin
                    if (clk_count < (CYCLES_PER_BIT - 1) / 2) begin
                        clk_count <= clk_count + 1;
                    end else begin
                        state <= DATA_BITS;
                        clk_count <= 0;
                        bit_index <= 0;
                    end
                end

                DATA_BITS: begin
                    if (clk_count < CYCLES_PER_BIT - 1) begin
                        clk_count <= clk_count + 1;
                    end else begin
                        clk_count <= 0;
                        rx_byte[bit_index] <= rx;
                        if (bit_index < 7) begin
                            bit_index <= bit_index + 1;
                        end else begin
                            state <= STOP;
                        end
                    end
                end

                STOP: begin
                    if (clk_count < CYCLES_PER_BIT - 1) begin
                        clk_count <= clk_count + 1;
                    end else begin
                        data <= rx_byte;
                        valid <= 1;
                        state <= IDLE;
                    end
                end
            endcase
        end
    end
endmodule

//============================================================================
// UART TX byte by byte, waits for completion
//============================================================================
module uart_tx_simple #(
    parameter CLK_FREQ = 100_000_000,
    parameter BAUD_RATE = 115200
)(
    input  logic clk,
    input  logic rst,
    input  logic [7:0] data_in,
    input  logic start,
    output logic tx,
    output logic done,
    output logic busy
);
    localparam integer CYCLES_PER_BIT = CLK_FREQ / BAUD_RATE;

    typedef enum logic [2:0] {IDLE, START_BIT, DATA_BITS, STOP_BIT, DONE} state_t;
    state_t state = IDLE;

    logic [15:0] clk_count = 0;
    logic [2:0] bit_index = 0;
    logic [7:0] tx_data = 0;

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            tx <= 1;
            done <= 0;
            busy <= 0;
            clk_count <= 0;
        end else begin
            done <= 0;

            case (state)
                IDLE: begin
                    tx <= 1;
                    busy <= 0;
                    clk_count <= 0;
                    if (start) begin
                        tx_data <= data_in;
                        busy <= 1;
                        state <= START_BIT;
                    end
                end

                START_BIT: begin
                    tx <= 0;
                    if (clk_count < CYCLES_PER_BIT - 1) begin
                        clk_count <= clk_count + 1;
                    end else begin
                        clk_count <= 0;
                        bit_index <= 0;
                        state <= DATA_BITS;
                    end
                end

                DATA_BITS: begin
                    tx <= tx_data[bit_index];
                    if (clk_count < CYCLES_PER_BIT - 1) begin
                        clk_count <= clk_count + 1;
                    end else begin
                        clk_count <= 0;
                        if (bit_index < 7) begin
                            bit_index <= bit_index + 1;
                        end else begin
                            state <= STOP_BIT;
                        end
                    end
                end

                STOP_BIT: begin
                    tx <= 1;
                    if (clk_count < CYCLES_PER_BIT - 1) begin
                        clk_count <= clk_count + 1;
                    end else begin
                        clk_count <= 0;
                        state <= DONE;
                    end
                end

                DONE: begin
                    done <= 1;
                    busy <= 0;
                    state <= IDLE;
                end
            endcase
        end
    end
endmodule

//============================================================================
// Packet Receiver - receives 18-byte market data packets
// Validates start marker (0xAA) to maintain synchronization
//============================================================================
module packet_receiver (
    input  logic clk,
    input  logic rst,
    input  logic [7:0] rx_byte,
    input  logic rx_valid,

    output logic [31:0] ticker,
    output logic [31:0] timestamp,
    output logic [23:0] ask_cents,
    output logic [23:0] bid_cents,
    output logic signed [15:0] position,
    output logic packet_ready
);
    logic [7:0] packet [0:17];
    logic [4:0] count = 0;

    always_ff @(posedge clk) begin
        if (rst) begin
            count <= 0;
            packet_ready <= 0;
        end else begin
            packet_ready <= 0;

            if (rx_valid) begin
                // Validate start marker for sync - if we're at count 0,
                // only accept 0xAA as start byte
                if (count == 0 && rx_byte != 8'hAA) begin
                    // Invalid start marker, stay at count 0 and wait for valid packet
                    count <= 0;
                end else begin
                    packet[count] <= rx_byte;

                    if (count == 17) begin
                        // All 18 bytes received, extract fields
                        ticker <= {packet[1], packet[2], packet[3], packet[4]};
                        timestamp <= {packet[5], packet[6], packet[7], packet[8]};
                        ask_cents <= {packet[9], packet[10], packet[11]};
                        bid_cents <= {packet[12], packet[13], packet[14]};
                        position <= {packet[15], packet[16]};
                        packet_ready <= 1;
                        count <= 0;
                    end else begin
                        count <= count + 1;
                    end
                end
            end
        end
    end
endmodule

//============================================================================
// Trading Algorithm - Arbitrage Strategy
//============================================================================
module trading_algorithm (
    input  logic clk,
    input  logic rst,
    input  logic packet_ready,
    input  logic [31:0] ticker,
    input  logic [23:0] ask_cents,
    input  logic [23:0] bid_cents,
    input  logic signed [15:0] position,
    input  logic [31:0] timestamp,

    output logic [31:0] response_ticker,
    output logic [1:0] action,
    output logic [15:0] quantity,
    output logic [7:0] order_type,
    output logic [23:0] limit_price,
    output logic [31:0] response_timestamp,
    output logic decision_ready
);
    always_ff @(posedge clk) begin
        if (rst) begin
            decision_ready <= 0;
        end else if (packet_ready) begin
            response_ticker <= ticker;
            response_timestamp <= timestamp;

            // Arbitrage: BUY when bid >= ask + 3 cents (inverted market)
            if (bid_cents >= (ask_cents + 24'd3)) begin
                action <= 2'd1;           // BUY
                quantity <= 16'd5;        // 5 shares
                order_type <= 8'd0;       // MARKET order
                limit_price <= ask_cents; // Buy at ask
            end
            // Reverse arbitrage: SELL when ask <= bid - 3 cents
            else if (ask_cents <= (bid_cents - 24'd3)) begin
                action <= 2'd2;           // SELL
                quantity <= 16'd5;        // 5 shares
                order_type <= 8'd0;       // MARKET order
                limit_price <= bid_cents; // Sell at bid
            end
            // Normal market: HOLD
            else begin
                action <= 2'd0;           // HOLD
                quantity <= 16'd0;
                order_type <= 8'd0;
                limit_price <= 24'd0;
            end

            decision_ready <= 1;
        end else begin
            decision_ready <= 0;
        end
    end
endmodule
//============================================================================
// Response Transmitter - sends 16 bytes one at a time
//============================================================================
module response_transmitter (
    input  logic clk,
    input  logic rst,
    input  logic decision_ready,
    input  logic [31:0] ticker,
    input  logic [1:0] action,
    input  logic [15:0] quantity,
    input  logic [7:0] order_type,
    input  logic [23:0] limit_price,
    input  logic [31:0] timestamp,
    input  logic tx_done,
    input  logic tx_busy,

    output logic [7:0] tx_data,
    output logic tx_start
);
    logic [7:0] response [0:15];
    logic [4:0] byte_index = 0;

    typedef enum logic [2:0] {IDLE, BUILD, SEND_BYTE, WAIT_DONE} state_t;
    state_t state = IDLE;

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            tx_start <= 0;
            byte_index <= 0;
        end else begin
            case (state)
                IDLE: begin
                    tx_start <= 0;
                    if (decision_ready) begin
                        state <= BUILD;
                    end
                end

                BUILD: begin
                    // Build response packet
                    response[0] <= 8'hBB;
                    response[1] <= ticker[31:24];
                    response[2] <= ticker[23:16];
                    response[3] <= ticker[15:8];
                    response[4] <= ticker[7:0];
                    response[5] <= {6'b0, action};
                    response[6] <= quantity[15:8];
                    response[7] <= quantity[7:0];
                    response[8] <= order_type;
                    response[9] <= limit_price[23:16];
                    response[10] <= limit_price[15:8];
                    response[11] <= limit_price[7:0];
                    response[12] <= timestamp[31:24];
                    response[13] <= timestamp[23:16];
                    response[14] <= timestamp[15:8];
                    response[15] <= timestamp[7:0];

                    byte_index <= 0;
                    state <= SEND_BYTE;
                end

                SEND_BYTE: begin
                    if (!tx_busy) begin
                        tx_data <= response[byte_index];
                        tx_start <= 1;
                        state <= WAIT_DONE;
                    end
                end

                WAIT_DONE: begin
                    tx_start <= 0;
                    if (tx_done) begin
                        if (byte_index < 15) begin
                            byte_index <= byte_index + 1;
                            state <= SEND_BYTE;
                        end else begin
                            state <= IDLE;
                        end
                    end
                end
            endcase
        end
    end
endmodule

//============================================================================
// Top Module
//============================================================================
module hft_top (
    input  logic CLK100MHZ,
    input  logic ck_rst,
    input  logic uart_rxd_out,
    output logic uart_txd_in,
    output logic [3:0] led
);
    logic rst;
    assign rst = ~ck_rst;

    // UART signals
    logic [7:0] rx_data;
    logic rx_valid;
    logic [7:0] tx_data;
    logic tx_start;
    logic tx_done;
    logic tx_busy;

    // Packet signals
    logic [31:0] ticker, timestamp;
    logic [23:0] ask_cents, bid_cents;
    logic signed [15:0] position;
    logic packet_ready;

    // Algorithm signals
    logic [31:0] response_ticker, response_timestamp;
    logic [1:0] action;
    logic [15:0] quantity;
    logic [7:0] order_type;
    logic [23:0] limit_price;
    logic decision_ready;

    // LED indicators
    logic packet_led = 0;
    logic decision_led = 0;

    always_ff @(posedge CLK100MHZ) begin
        if (packet_ready) packet_led <= ~packet_led;
        if (decision_ready) decision_led <= ~decision_led;
    end

    assign led[0] = packet_led;
    assign led[1] = decision_led;
    assign led[2] = tx_busy;
    assign led[3] = 1'b1;

    // Instantiate modules
    uart_rx uart_receiver (
        .clk(CLK100MHZ),
        .rst(rst),
        .rx(uart_rxd_out),
        .data(rx_data),
        .valid(rx_valid)
    );

    uart_tx_simple uart_transmitter (
        .clk(CLK100MHZ),
        .rst(rst),
        .data_in(tx_data),
        .start(tx_start),
        .tx(uart_txd_in),
        .done(tx_done),
        .busy(tx_busy)
    );

    packet_receiver pkt_rx (
        .clk(CLK100MHZ),
        .rst(rst),
        .rx_byte(rx_data),
        .rx_valid(rx_valid),
        .ticker(ticker),
        .timestamp(timestamp),
        .ask_cents(ask_cents),
        .bid_cents(bid_cents),
        .position(position),
        .packet_ready(packet_ready)
    );

    trading_algorithm algo (
        .clk(CLK100MHZ),
        .rst(rst),
        .packet_ready(packet_ready),
        .ticker(ticker),
        .ask_cents(ask_cents),
        .bid_cents(bid_cents),
        .position(position),
        .timestamp(timestamp),
        .response_ticker(response_ticker),
        .action(action),
        .quantity(quantity),
        .order_type(order_type),
        .limit_price(limit_price),
        .response_timestamp(response_timestamp),
        .decision_ready(decision_ready)
    );

    response_transmitter resp_tx (
        .clk(CLK100MHZ),
        .rst(rst),
        .decision_ready(decision_ready),
        .ticker(response_ticker),
        .action(action),
        .quantity(quantity),
        .order_type(order_type),
        .limit_price(limit_price),
        .timestamp(response_timestamp),
        .tx_done(tx_done),
        .tx_busy(tx_busy),
        .tx_data(tx_data),
        .tx_start(tx_start)
    );

endmodule
