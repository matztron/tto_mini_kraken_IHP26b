// Tiny Tapeout 1x1 programmable PIO tile — load IMEM + config via pins.
//
// Run mode (uio[7]=0):
//   ui[1:0]   gpio_in (also LSBs of TX byte when pushing)
//   ui[7:0]   TX byte for UART programs
//   uio[0]    tx_push (rising edge)
//   uio[1]    sm_enable (level, with ena)
//   uio[2]    sm_restart (rising edge)
//   uio[3]    rx_pop (rising edge)
//   uio[4]    rx_hold ack (clear latched RX byte on uo)
//   uo[1:0]   PIO GPIO out
//   uo[2]     tx_full
//   uo[3]     rx_empty
//   uo[7:4]   irq_flags[3:0]  (or full uo[7:0]=rx byte when rx_hold_valid)
//
// Config mode (uio[7]=1): see kraken_tt_loader.sv
module tt_um_kraken_mini (
  input  logic [7:0] ui_in,
  output logic [7:0] uo_out,
  input  logic [7:0] uio_in,
  output logic [7:0] uio_out,
  output logic [7:0] uio_oe,
  input  logic       ena,
  input  logic       clk,
  input  logic       rst_n
);
  typedef kraken_pkg::instr_t instr_t;
  typedef kraken_pkg::data_t  data_t;
  typedef kraken_pkg::pc_t    pc_t;
  typedef kraken_pkg::gpio_t  gpio_t;
  localparam int unsigned GPIO_W  = kraken_pkg::GPIO_W;
  localparam int unsigned NUM_IRQ = kraken_pkg::NUM_IRQ;

  logic cfg_mode;
  logic imem_wr_en;
  pc_t    imem_wr_addr;
  instr_t imem_wr_data;
  logic       exec_wr;
  logic [7:0] exec_data;
  logic       pin_wr;
  logic [7:0] pin_data;
  logic       shift_wr;
  logic [7:0] shift_data;
  logic       thresh_wr;
  logic [7:0] thresh_data;
  logic       inpin_wr;
  logic [7:0] inpin_data;
  logic       clkdiv_lo_wr, clkdiv_hi_wr;
  logic [7:0] clkdiv_byte;

  pc_t   wrap_bottom, wrap_top;
  logic  side_en, side_pindir;
  logic [2:0] set_count, sideset_count;
  logic [5:0] out_count;
  logic [4:0] in_base, jmp_pin;
  logic in_shiftdir, out_shiftdir, autopush, autopull;
  logic [4:0] push_thresh, pull_thresh;
  logic [15:0] clkdiv_int;

  logic push_raw, push_q, tx_push;
  logic restart_raw, restart_q, sm_restart;
  logic rx_pop_raw, rx_pop_q, rx_pop;
  logic sm_enable;
  logic clk_en;
  logic [15:0] div_cnt;

  logic tx_full;
  data_t tx_data;
  gpio_t gpio_out, gpio_oe, gpio_in;
  pc_t   imem_addr;
  instr_t imem_data;

  logic [NUM_IRQ-1:0] irq_flags, irq_set, irq_clr;
  data_t rx_data;
  logic  rx_empty;
  pc_t   dbg_pc_unused;
  logic [3:0] tx_lv_u, rx_lv_u;
  logic f0, f1, f2, f3;
  logic [4:0] dbg_delay_u;
  logic dbg_exec_u, dbg_stall_u;

  logic [7:0] rx_hold;
  logic       rx_hold_valid;

  localparam logic [4:0] SET_BASE     = 5'd0;
  localparam logic [4:0] OUT_BASE     = 5'd0;
  localparam logic [4:0] SIDESET_BASE = 5'd0;

  assign push_raw    = !cfg_mode && uio_in[0];
  assign restart_raw = !cfg_mode && uio_in[2];
  assign rx_pop_raw  = !cfg_mode && uio_in[3];
  assign sm_enable   = ena && !cfg_mode && uio_in[1];
  assign tx_data     = kraken_pkg::data_t'(ui_in);
  assign gpio_in     = kraken_pkg::gpio_t'(ui_in[GPIO_W-1:0]);

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      push_q     <= 1'b0;
      restart_q  <= 1'b0;
      rx_pop_q   <= 1'b0;
    end else begin
      push_q    <= push_raw;
      restart_q <= restart_raw;
      rx_pop_q  <= rx_pop_raw;
    end
  end

  assign tx_push    = sm_enable && push_raw && !push_q && !tx_full;
  assign sm_restart = sm_enable && restart_raw && !restart_q;
  assign rx_pop     = sm_enable && rx_pop_raw && !rx_pop_q && !rx_empty;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      div_cnt <= '0;
      clk_en  <= 1'b1;
    end else if (!sm_enable) begin
      div_cnt <= '0;
      clk_en  <= 1'b1;
    end else if (clkdiv_int <= 16'd1) begin
      clk_en <= 1'b1;
    end else if (div_cnt >= clkdiv_int - 16'd1) begin
      div_cnt <= '0;
      clk_en  <= 1'b1;
    end else begin
      div_cnt <= div_cnt + 16'd1;
      clk_en  <= 1'b0;
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      irq_flags <= '0;
    else
      irq_flags <= (irq_flags | irq_set) & ~irq_clr;
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rx_hold       <= 8'h00;
      rx_hold_valid <= 1'b0;
    end else if (sm_restart) begin
      rx_hold_valid <= 1'b0;
    end else if (rx_pop) begin
      rx_hold       <= rx_data;
      rx_hold_valid <= 1'b1;
    end else if (!cfg_mode && uio_in[4]) begin
      rx_hold_valid <= 1'b0;
    end
  end

  kraken_tt_loader u_loader (
    .clk              (clk),
    .rst_n            (rst_n),
    .ui_in            (ui_in),
    .uio_in           (uio_in),
    .cfg_mode         (cfg_mode),
    .imem_wr_en       (imem_wr_en),
    .imem_wr_addr     (imem_wr_addr),
    .imem_wr_data     (imem_wr_data),
    .exec_wr          (exec_wr),
    .exec_data        (exec_data),
    .pin_wr           (pin_wr),
    .pin_data         (pin_data),
    .shift_wr         (shift_wr),
    .shift_data       (shift_data),
    .thresh_wr        (thresh_wr),
    .thresh_data      (thresh_data),
    .inpin_wr         (inpin_wr),
    .inpin_data       (inpin_data),
    .clkdiv_lo_wr     (clkdiv_lo_wr),
    .clkdiv_hi_wr     (clkdiv_hi_wr),
    .clkdiv_byte      (clkdiv_byte)
  );

  kraken_tt_cfg u_cfg (
    .clk              (clk),
    .rst_n            (rst_n),
    .exec_wr          (exec_wr),
    .exec_data        (exec_data),
    .pin_wr           (pin_wr),
    .pin_data         (pin_data),
    .shift_wr         (shift_wr),
    .shift_data       (shift_data),
    .thresh_wr        (thresh_wr),
    .thresh_data      (thresh_data),
    .inpin_wr         (inpin_wr),
    .inpin_data       (inpin_data),
    .clkdiv_lo_wr     (clkdiv_lo_wr),
    .clkdiv_hi_wr     (clkdiv_hi_wr),
    .clkdiv_byte      (clkdiv_byte),
    .wrap_bottom      (wrap_bottom),
    .wrap_top         (wrap_top),
    .side_en          (side_en),
    .side_pindir      (side_pindir),
    .set_count        (set_count),
    .out_count        (out_count),
    .sideset_count    (sideset_count),
    .in_base          (in_base),
    .jmp_pin          (jmp_pin),
    .in_shiftdir      (in_shiftdir),
    .out_shiftdir     (out_shiftdir),
    .autopush         (autopush),
    .autopull         (autopull),
    .push_thresh      (push_thresh),
    .pull_thresh      (pull_thresh),
    .clkdiv_int       (clkdiv_int)
  );

  kraken_imem u_imem (
    .clk      (clk),
    .rst_n    (rst_n),
    .wr_en    (imem_wr_en),
    .wr_addr  (imem_wr_addr),
    .wr_data  (imem_wr_data),
    .rd_addr  (imem_addr),
    .rd_data  (imem_data)
  );

  kraken_sm #(
    .ENABLE_FJOIN(1'b0),
    .ENABLE_RX(1'b1)
  ) u_sm (
    .clk            (clk),
    .rst_n          (rst_n),
    .enable         (sm_enable),
    .clk_en         (clk_en),
    .sm_restart     (sm_restart),
    .host_exec_stb  (1'b0),
    .host_exec_instr('0),
    .sm_id          (2'd0),
    .wrap_bottom    (wrap_bottom),
    .wrap_top       (wrap_top),
    .set_base       (SET_BASE),
    .set_count      (set_count),
    .out_base       (OUT_BASE),
    .out_count      (out_count),
    .in_base        (in_base),
    .jmp_pin        (jmp_pin),
    .sideset_base   (SIDESET_BASE),
    .sideset_count  (sideset_count),
    .side_en        (side_en),
    .side_pindir    (side_pindir),
    .in_shiftdir    (in_shiftdir),
    .out_shiftdir   (out_shiftdir),
    .push_thresh    (push_thresh),
    .pull_thresh    (pull_thresh),
    .autopush       (autopush),
    .autopull       (autopull),
    .fjoin_tx       (1'b0),
    .fjoin_rx       (1'b0),
    .status_sel     (1'b0),
    .status_n       (4'd0),
    .imem_addr      (imem_addr),
    .imem_data      (imem_data),
    .gpio_in        (gpio_in),
    .gpio_out       (gpio_out),
    .gpio_oe        (gpio_oe),
    .irq_flags      (irq_flags),
    .irq_set        (irq_set),
    .irq_clr        (irq_clr),
    .tx_push        (tx_push),
    .tx_data        (tx_data),
    .tx_full        (tx_full),
    .rx_pop         (rx_pop),
    .rx_data        (rx_data),
    .rx_empty       (rx_empty),
    .dbg_pc         (dbg_pc_unused),
    .tx_level_o     (tx_lv_u),
    .rx_level_o     (rx_lv_u),
    .fdbg_txover    (f0),
    .fdbg_txunder   (f1),
    .fdbg_rxover    (f2),
    .fdbg_rxunder   (f3),
    .dbg_delay      (dbg_delay_u),
    .dbg_executing  (dbg_exec_u),
    .dbg_stalled    (dbg_stall_u)
  );

  logic [7:0] status_uo;
  assign status_uo = {irq_flags, rx_empty, tx_full, gpio_out[GPIO_W-1:0]};

  assign uo_out  = rx_hold_valid ? rx_hold : status_uo;
  assign uio_out = '0;
  assign uio_oe  = '0;

  wire unused = |{dbg_pc_unused, tx_lv_u, rx_lv_u, f0, f1, f2, f3,
                  dbg_delay_u, dbg_exec_u, dbg_stall_u, gpio_oe};
endmodule
