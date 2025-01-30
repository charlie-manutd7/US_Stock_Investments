let currentContext = {};
// Removing backtest chart variable
// let backtestChart = null;

// Configuration
const config = {
  // Use production URL if available, otherwise fallback to localhost
  apiBaseUrl:
    "https://stock-options-tool-api.onrender.com" || "http://localhost:8080",
};

document.addEventListener("DOMContentLoaded", function () {
  // Set default date to today
  document.getElementById("endDate").valueAsDate = new Date();

  // Initialize form
  document
    .getElementById("analysisForm")
    .addEventListener("submit", handleAnalysisSubmit);
});

async function handleAnalysisSubmit(event) {
  event.preventDefault();

  // Show loading state
  document.getElementById("loadingSpinner").style.display = "block";
  document.getElementById("analysisResults").style.display = "none";
  document.getElementById("errorMessage").style.display = "none";

  // Get form data
  const ticker = document.getElementById("ticker").value.toUpperCase();
  const endDate = document.getElementById("endDate").value;
  const numNews = document.getElementById("numNews").value;

  try {
    const response = await fetch(`${config.apiBaseUrl}/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ticker: ticker,
        end_date: endDate,
        num_of_news: parseInt(numNews),
      }),
    });

    const data = await response.json();

    // Log the complete response for debugging
    console.log("Analysis Response:", data);

    if (data.success) {
      currentContext = data;
      if (!data.current_analysis) {
        showError("Missing current analysis data");
        console.error("Missing current_analysis in response:", data);
      } else if (!data.current_analysis.analysis) {
        showError("Missing analysis details");
        console.error(
          "Missing analysis in current_analysis:",
          data.current_analysis
        );
      } else {
        updateAnalysisDisplay(data);
      }
    } else {
      showError(data.error || "Analysis failed without specific error message");
      console.error("Analysis failed:", data);
    }
  } catch (error) {
    showError("Failed to fetch analysis results");
    console.error("Analysis request failed:", error);
  }

  hideLoading();
}

function updateAnalysisDisplay(data) {
  const currentAnalysis = document.getElementById("currentAnalysis");
  const momentumAnalysis = document.getElementById("momentumAnalysis");
  const optionsStrategy = document.getElementById("optionsStrategy");
  const longTermReasoning = document.getElementById("longTermReasoning");
  const shortTermReasoning = document.getElementById("shortTermReasoning");

  // Helper function to create tooltip spans
  const withTooltip = (text, tooltip) => `
    <span class="tooltip-trigger">
      ${text} <i class="fas fa-question-circle"></i>
      <span class="tooltip-text">${tooltip}</span>
    </span>
  `;

  // Update long-term analysis section
  if (data.current_analysis && data.current_analysis.analysis) {
    const analysis = data.current_analysis.analysis;

    currentAnalysis.innerHTML = `
      <div class="row">
        <div class="col-md-6">
          <h6>${withTooltip(
            "Trading Decision",
            "Recommended trading action based on comprehensive analysis"
          )}</h6>
          <table class="table">
            <tr>
              <td>${withTooltip(
                "Action",
                "The recommended trading action to take"
              )}:</td>
              <td class="text-end">${analysis.action.toUpperCase()}</td>
            </tr>
            <tr>
              <td>${withTooltip(
                "Quantity",
                "Suggested number of shares/contracts to trade"
              )}:</td>
              <td class="text-end">${analysis.quantity}</td>
            </tr>
            <tr>
              <td>${withTooltip(
                "Confidence",
                "Level of certainty in the trading recommendation"
              )}:</td>
              <td class="text-end">${(analysis.confidence * 100).toFixed(
                0
              )}%</td>
            </tr>
          </table>
        </div>
        <div class="col-md-6">
          <h6>${withTooltip(
            "Price Targets",
            "Key price levels for trading decisions"
          )}</h6>
          <table class="table">
            <tr>
              <td>${withTooltip(
                "Current Price",
                "Latest trading price of the stock"
              )}:</td>
              <td class="text-end">$${analysis.price_targets.current_price.toFixed(
                2
              )}</td>
            </tr>
            <tr>
              <td>${withTooltip(
                "Fair Value",
                "Estimated intrinsic value of the stock"
              )}:</td>
              <td class="text-end">$${analysis.price_targets.fair_value.toFixed(
                2
              )}</td>
            </tr>
            <tr>
              <td>${withTooltip(
                "Buy Target",
                "Price level at which to consider buying"
              )}:</td>
              <td class="text-end">$${analysis.price_targets.buy_target.toFixed(
                2
              )}</td>
            </tr>
            <tr>
              <td>${withTooltip(
                "Sell Target",
                "Price level at which to consider selling"
              )}:</td>
              <td class="text-end">$${analysis.price_targets.sell_target.toFixed(
                2
              )}</td>
            </tr>
          </table>
        </div>
      </div>
    `;

    // Update options strategy section
    const optionsStrategyData = analysis.options_strategy;
    if (
      optionsStrategyData &&
      optionsStrategyData.strategy !== "No strategy recommended"
    ) {
      displayOptionsStrategy(optionsStrategyData, optionsStrategy);
    } else {
      optionsStrategy.innerHTML =
        "<p>No options strategy recommended at this time.</p>";
    }

    // Update analysis reasoning section
    const reasoning = analysis.reasoning;
    const agentSignals = analysis.agent_signals;
    if (agentSignals && agentSignals.length > 0) {
      let reasoningHtml = '<div class="analysis-reasoning">';

      // Summary section
      if (reasoning.summary) {
        reasoningHtml += `<div class="mb-3">
          <h6>${withTooltip(
            "Summary",
            "Overall analysis summary based on all signals"
          )}</h6>
          <p>${reasoning.summary}</p>
        </div>`;
      }

      // Agent Signals section
      reasoningHtml += `<div class="mb-3">
        <h6>${withTooltip(
          "Agent Analysis",
          "Individual analysis from each specialized agent"
        )}</h6>
        <table class="table">
          <thead>
            <tr>
              <th>${withTooltip("Agent", "Specialized analysis agent")}</th>
              <th>${withTooltip("Signal", "Trading signal from the agent")}</th>
              <th class="text-end">${withTooltip(
                "Confidence",
                "Level of certainty in the signal"
              )}</th>
            </tr>
          </thead>
          <tbody>
            ${agentSignals
              .filter((signal) => !signal.agent.includes("options_advisor"))
              .map(
                (signal) => `
              <tr>
                <td>${formatAgentName(signal.agent)}</td>
                <td><span class="signal-${signal.signal.toLowerCase()}">${signal.signal.toUpperCase()}</span></td>
                <td class="text-end">${signal.confidence}</td>
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      </div>`;

      reasoningHtml += "</div>";
      longTermReasoning.innerHTML = reasoningHtml;

      // Add signal color styles if not present
      if (!document.querySelector("style#signal-styles")) {
        const style = document.createElement("style");
        style.id = "signal-styles";
        style.textContent = `
          .signal-bullish {
            color: #28a745;
            font-weight: bold;
          }
          .signal-bearish {
            color: #dc3545;
            font-weight: bold;
          }
          .signal-neutral {
            color: #6c757d;
            font-weight: bold;
          }
        `;
        document.head.appendChild(style);
      }
    } else {
      longTermReasoning.innerHTML =
        '<div class="text-muted">No analysis signals available.</div>';
    }

    // Update short-term momentum analysis
    if (analysis.momentum_analysis) {
      const momentum = analysis.momentum_analysis;
      const availableMomentumFields = Object.keys(momentum);

      if (availableMomentumFields.length === 0) {
        momentumAnalysis.innerHTML = `
          <div class="alert alert-warning">
            Momentum analysis object exists but contains no data.
          </div>`;
      } else {
        momentumAnalysis.innerHTML = `
          <div class="row">
            <div class="col-md-6">
              <h6>${withTooltip(
                "Momentum Indicators",
                "Technical indicators measuring the strength and speed of price movements"
              )}</h6>
              <table class="table">
                <tr>
                  <td>${withTooltip(
                    "Price Momentum",
                    "Rate of change in price over the last 5 periods"
                  )}:</td>
                  <td class="text-end">
                    <span class="momentum-indicator momentum-${
                      momentum.price_momentum.signal
                    }">${momentum.price_momentum.value}%</span>
                  </td>
                </tr>
                <tr>
                  <td>${withTooltip(
                    "Volume Momentum",
                    "Rate of change in trading volume relative to recent average"
                  )}:</td>
                  <td class="text-end">
                    <span class="momentum-indicator momentum-${
                      momentum.volume_momentum.signal
                    }">${momentum.volume_momentum.value}%</span>
                  </td>
                </tr>
                <tr>
                  <td>${withTooltip(
                    "RSI",
                    "Relative Strength Index - measures overbought/oversold conditions (0-100)"
                  )}:</td>
                  <td class="text-end">${momentum.rsi.toFixed(2)}</td>
                </tr>
              </table>
            </div>
            <div class="col-md-6">
              <h6>${withTooltip(
                "Short-term Targets",
                "Key price levels for short-term trading decisions"
              )}</h6>
              <table class="table">
                <tr>
                  <td>${withTooltip(
                    "Current Price",
                    "Latest trading price of the stock"
                  )}:</td>
                  <td class="text-end">$${momentum.current_price.toFixed(
                    2
                  )}</td>
                </tr>
                <tr>
                  <td>${withTooltip(
                    "Target Price",
                    "Expected price target based on momentum and volatility"
                  )}:</td>
                  <td class="text-end">$${momentum.target_price.toFixed(2)}</td>
                </tr>
                <tr>
                  <td>${withTooltip(
                    "Support",
                    "Price level where buying pressure is expected to prevent further decline"
                  )}:</td>
                  <td class="text-end">$${momentum.support_level.toFixed(
                    2
                  )}</td>
                </tr>
                <tr>
                  <td>${withTooltip(
                    "Resistance",
                    "Price level where selling pressure is expected to prevent further rise"
                  )}:</td>
                  <td class="text-end">$${momentum.resistance_level.toFixed(
                    2
                  )}</td>
                </tr>
                <tr>
                  <td>${withTooltip(
                    "Stop Loss",
                    "Recommended price level to exit position to limit potential losses"
                  )}:</td>
                  <td class="text-end">$${momentum.stop_loss.toFixed(2)}</td>
                </tr>
              </table>
            </div>
          </div>
          <div class="row mt-3">
            <div class="col-12">
              <h6>${withTooltip(
                "Trading Signal",
                "Short-term trading recommendation based on momentum analysis"
              )}</h6>
              <table class="table">
                <tr>
                  <td>${withTooltip(
                    "Action",
                    "Recommended trading action based on momentum"
                  )}:</td>
                  <td class="text-end">${momentum.signal.toUpperCase()}</td>
                </tr>
                <tr>
                  <td>${withTooltip(
                    "Timeframe",
                    "Expected duration for the trading signal"
                  )}:</td>
                  <td class="text-end">${
                    momentum.timeframe || "Short-term"
                  }</td>
                </tr>
                <tr>
                  <td>${withTooltip(
                    "Confidence",
                    "Level of certainty in the momentum signal"
                  )}:</td>
                  <td class="text-end">${(momentum.confidence * 100).toFixed(
                    0
                  )}%</td>
                </tr>
              </table>
            </div>
          </div>
        `;
      }

      // Enhanced momentum reasoning display with tooltips
      if (momentum.reasoning && momentum.reasoning.length > 0) {
        shortTermReasoning.innerHTML = `
          <ul>
            ${momentum.reasoning.map((reason) => `<li>${reason}</li>`).join("")}
          </ul>`;
      } else {
        shortTermReasoning.innerHTML = `
          <div class="text-muted">
            No momentum reasoning available.
          </div>`;
      }
    } else {
      momentumAnalysis.innerHTML = `
        <div class="alert alert-warning">
          No momentum analysis available in the response.
        </div>`;
    }

    // Add Font Awesome if not already present
    if (!document.querySelector('link[href*="font-awesome"]')) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href =
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css";
      document.head.appendChild(link);
    }

    // Add tooltip styles if not already present
    if (!document.querySelector("style#tooltip-styles")) {
      const style = document.createElement("style");
      style.id = "tooltip-styles";
      style.textContent = `
        .tooltip-trigger {
          position: relative;
          cursor: help;
        }
        
        .tooltip-trigger i {
          font-size: 0.8em;
          color: #6c757d;
          margin-left: 2px;
        }
        
        .tooltip-text {
          visibility: hidden;
          position: absolute;
          left: 50%;
          transform: translateX(-50%);
          bottom: 100%;
          background-color: #333;
          color: white;
          padding: 5px 10px;
          border-radius: 4px;
          font-size: 0.8em;
          white-space: nowrap;
          z-index: 1;
          opacity: 0;
          transition: opacity 0.3s;
        }
        
        .tooltip-trigger:hover .tooltip-text {
          visibility: visible;
          opacity: 1;
        }
        
        .tooltip-text::after {
          content: "";
          position: absolute;
          top: 100%;
          left: 50%;
          margin-left: -5px;
          border-width: 5px;
          border-style: solid;
          border-color: #333 transparent transparent transparent;
        }
      `;
      document.head.appendChild(style);
    }
  } else {
    currentAnalysis.innerHTML =
      '<div class="alert alert-warning">No analysis data available</div>';
  }

  // Display error if present
  if (data.error) {
    showError(data.error);
  }
}

function formatIndustryType(type) {
  if (!type) return "N/A";
  return type
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function displayOptionsStrategy(strategy, container) {
  if (!strategy || strategy.strategy === "No strategy recommended") {
    container.innerHTML =
      '<div class="text-muted">No options strategy recommended at this time.</div>';
    return;
  }

  // Format implementation details
  const implementation = strategy.implementation || {};
  const strikes = implementation.strikes || {};
  const premium = implementation.premium || {};
  const expirations = implementation.expirations || {};

  // Helper function to create tooltip spans
  const withTooltip = (text, tooltip) => `
    <span class="tooltip-trigger">
      ${text} <i class="fas fa-question-circle"></i>
      <span class="tooltip-text">${tooltip}</span>
    </span>
  `;

  const html = `
    <div class="strategy-details">
      <div class="mb-3">
        <h6 class="mb-2">${strategy.strategy.toUpperCase()}</h6>
        <p class="text-muted mb-2"><strong>${withTooltip(
          "Outlook",
          "The market perspective and reasoning behind this strategy"
        )}:</strong> ${strategy.rationale || ""}</p>
        <p class="text-muted mb-2"><strong>${withTooltip(
          "Risk Profile",
          "Assessment of the strategy's risk level and characteristics"
        )}:</strong> ${strategy.risk_profile || ""}</p>
      </div>
      
      <div class="mb-3">
        <h6 class="mb-2">Implementation Details:</h6>
        <table class="table table-sm">
          <tr>
            <td>${withTooltip(
              "RECOMMENDED EXPIRATION",
              "The suggested time until option expiration based on the strategy"
            )}:</td>
            <td>${implementation.recommended_expiration || "N/A"}</td>
          </tr>
          <tr>
            <td>${withTooltip(
              "EXPIRATIONS",
              "Available expiration timeframes with different risk/reward profiles"
            )}:</td>
            <td>
              Conservative: ${expirations.conservative || "N/A"}<br>
              Moderate: ${expirations.moderate || "N/A"}<br>
              Aggressive: ${expirations.aggressive || "N/A"}
            </td>
          </tr>
          <tr>
            <td>${withTooltip(
              "RECOMMENDED STRIKE",
              "The suggested price at which the option can be exercised"
            )}:</td>
            <td>$${Number(implementation.recommended_strike || 0).toFixed(
              2
            )}</td>
          </tr>
          <tr>
            <td>${withTooltip(
              "STRIKES",
              "Available strike prices with different risk/reward profiles"
            )}:</td>
            <td>
              Conservative: $${Number(strikes.conservative || 0).toFixed(2)}<br>
              Moderate: $${Number(strikes.moderate || 0).toFixed(2)}<br>
              Aggressive: $${Number(strikes.aggressive || 0).toFixed(2)}
            </td>
          </tr>
          <tr>
            <td>${withTooltip(
              "PREMIUM",
              "The amount received for selling the put option"
            )}:</td>
            <td>$${Number(premium.target_premium || 0).toFixed(2)}</td>
          </tr>
          <tr>
            <td>${withTooltip(
              "MAX PROFIT",
              "Maximum potential gain from the strategy (limited to premium received for cash-secured puts)"
            )}:</td>
            <td>$${Number(implementation.max_profit || 0).toFixed(2)}</td>
          </tr>
          <tr>
            <td>${withTooltip(
              "MAX LOSS",
              "Maximum potential loss (strike price minus premium received)"
            )}:</td>
            <td>$${Number(implementation.max_loss || 0).toFixed(2)}</td>
          </tr>
        </table>
      </div>
    </div>

    <style>
      .tooltip-trigger {
        position: relative;
        cursor: help;
      }
      
      .tooltip-trigger i {
        font-size: 0.8em;
        color: #6c757d;
        margin-left: 2px;
      }
      
      .tooltip-text {
        visibility: hidden;
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        bottom: 100%;
        background-color: #333;
        color: white;
        padding: 5px 10px;
        border-radius: 4px;
        font-size: 0.8em;
        white-space: nowrap;
        z-index: 1;
        opacity: 0;
        transition: opacity 0.3s;
      }
      
      .tooltip-trigger:hover .tooltip-text {
        visibility: visible;
        opacity: 1;
      }
      
      .tooltip-text::after {
        content: "";
        position: absolute;
        top: 100%;
        left: 50%;
        margin-left: -5px;
        border-width: 5px;
        border-style: solid;
        border-color: #333 transparent transparent transparent;
      }
    </style>
  `;

  container.innerHTML = html;

  // Add Font Awesome if not already present
  if (!document.querySelector('link[href*="font-awesome"]')) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href =
      "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css";
    document.head.appendChild(link);
  }
}

function addMessage(text, type) {
  const container = document.getElementById("chatMessages");
  const messageDiv = document.createElement("div");
  messageDiv.className = `message ${type}-message`;
  messageDiv.textContent = text;
  container.appendChild(messageDiv);
  container.scrollTop = container.scrollHeight;
}

function showLoading() {
  document.getElementById("currentAnalysis").classList.add("loading");
  document.getElementById("optionsStrategy").classList.add("loading");
}

function hideLoading() {
  document.getElementById("currentAnalysis").classList.remove("loading");
  document.getElementById("optionsStrategy").classList.remove("loading");
}

function showError(message) {
  const errorDiv = document.createElement("div");
  errorDiv.className = "error-message";
  errorDiv.textContent = message;
  document.getElementById("currentAnalysis").prepend(errorDiv);
  setTimeout(() => errorDiv.remove(), 5000);
}

function formatAgentName(agentName) {
  // Remove _agent suffix and capitalize each word
  return agentName
    .replace("_agent", "")
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
