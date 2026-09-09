import { describe, expect, it } from "vitest";
import entry from "./index.js";
import { getToolPluginMetadata } from "openclaw/plugin-sdk/tool-plugin";

describe("quant-research", () => {
  it("declares 10 tool metadata", () => {
    const tools = getToolPluginMetadata(entry)?.tools.map((tool) => tool.name).sort();
    expect(tools).toEqual([
      "quant_generate_pine_script",
      "quant_get_top_results",
      "quant_run_backtest",
      "quant_run_strategy",
      "quant_run_walk_forward",
      "quant_scan_ma_params",
      "quant_scan_multi_stocks",
      "quant_scan_strategy_params",
      "quant_simulate_stop_loss",
      "quant_validate_strategy",
    ]);
  });
});
