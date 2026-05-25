# =============================================================================
# Securitisation Portfolio Analysis
# =============================================================================
# This script simulates a hypothetical portfolio of securitisation transactions, computes
# tranche-level metrics (attachment/detachment points, capital benefit,
# NPL classification), and produces a multi-panel dashboard with different metrics fit for supervisory purposes.
#
# Methodology references:
#   - CRR Article 242 (tranche seniority definitions)
#   - CRR Articles 259-264 (SEC-SA / SEC-IRBA / SEC-ERBA hierarchy)
#   - EBA COREP C14.00 / C14.01 reporting framework
# =============================================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.patches as mpatches
import seaborn as sns
from matplotlib.gridspec import GridSpec

# =============================================================================
# 1. SIMULATE SECURITISATION TRANSACTION PORTFOLIO
# =============================================================================

np.random.seed(42)
N = 40  # number of transactions

# Regulatory approaches (CRR hierarchy)
APPROACHES = ["SEC-SA", "SEC-IRBA", "SEC-ERBA", "1250%"]
approach_weights = [0.45, 0.30, 0.15, 0.10]

# Asset classes
ASSET_CLASSES = ["Residential Mortgages", "SME Loans", "Auto Loans",
                 "Consumer Credit", "Corporate Loans"]

# Generate transaction identifiers
transaction_ids = [f"SEC-{str(i+1).zfill(3)}" for i in range(N)]

# Generate attachment and detachment points (A < D, both between 0 and 1)
attachment   = np.round(np.random.uniform(0.00, 0.10, N), 4)  # first-loss / junior
detachment   = np.round(attachment + np.random.uniform(0.05, 0.25, N), 4)
detachment   = np.minimum(detachment, 1.0)

# Notional pool sizes (EUR millions)
notional     = np.round(np.random.uniform(100, 3000, N), 1)

# Risk weight of underlying pool (used in capital benefit calc)
pool_rw      = np.round(np.random.uniform(0.20, 1.00, N), 2)

# Retained interest (originator skin-in-the-game, min 5% per CRR Art. 6)
retention    = np.round(np.random.uniform(0.05, 0.20, N), 2)

# NPL ratio of underlying pool
npl_ratio    = np.round(np.random.uniform(0.01, 0.30, N), 4)

# Excess spread (annualised)
excess_spread = np.round(np.random.uniform(0.00, 0.05, N), 4)

# Approach and asset class
approach     = np.random.choice(APPROACHES, N, p=approach_weights)
asset_class  = np.random.choice(ASSET_CLASSES, N)

# Build dataframe
df = pd.DataFrame({
    "Transaction_ID":  transaction_ids,
    "Asset_Class":     asset_class,
    "Approach":        approach,
    "Notional_EURm":   notional,
    "Attachment":      attachment,
    "Detachment":      detachment,
    "Pool_RW":         pool_rw,
    "Retention":       retention,
    "NPL_Ratio":       npl_ratio,
    "Excess_Spread":   excess_spread,
})

# =============================================================================
# 2. TRANCHE CLASSIFICATION (CRR Art. 242)
# =============================================================================
# Senior:     detachment == 1.0  (most protected)
# Mezzanine:  0 < attachment < detachment < 1
# First Loss: attachment == 0    (first to absorb losses)

def classify_tranche(row):
    if row["Attachment"] == 0.0:
        return "First Loss"
    elif row["Detachment"] >= 0.95:
        return "Senior"
    else:
        return "Mezzanine"

df["Tranche_Type"] = df.apply(classify_tranche, axis=1)

# Tranche thickness (detachment - attachment)
df["Tranche_Thickness"] = np.round(df["Detachment"] - df["Attachment"], 4)

# =============================================================================
# 3. NPL CLASSIFICATION
# =============================================================================
# Flag transactions where underlying pool NPL ratio >= 20%
# (simplified proxy for NPL securitisation per EBA guidelines)

NPL_THRESHOLD = 0.20
df["Is_NPL_Sec"] = df["NPL_Ratio"] >= NPL_THRESHOLD

# =============================================================================
# 4. CAPITAL BENEFIT CALCULATION
# =============================================================================
# Pre-securitisation RWA:
#   RWA_pre = Notional * Pool_RW
#
# Post-securitisation RWA (simplified):
#   For retained tranche only (retention % of notional)
#   RWA_post = retained_notional * tranche_rw
#   where tranche_rw = 1.0 for 1250% approach, else pool_rw * thickness factor
#
# Capital Benefit (bps of RWA):
#   CB = (RWA_pre - RWA_post) / RWA_pre * 10000

df["RWA_pre_EURm"]  = np.round(df["Notional_EURm"] * df["Pool_RW"], 2)

# Simplified post-RWA: 1250% approach = full deduction (no RWA benefit)
# Others: risk weight relief proportional to transferred tranche thickness
transferred_thickness = df["Tranche_Thickness"] * (1 - df["Retention"])

df["RWA_post_EURm"] = np.where(
    df["Approach"] == "1250%",
    df["RWA_pre_EURm"],   # no benefit
    np.round(df["RWA_pre_EURm"] * (1 - transferred_thickness * df["Pool_RW"]), 2)
)

df["RWA_Benefit_EURm"] = np.round(df["RWA_pre_EURm"] - df["RWA_post_EURm"], 2)

df["Capital_Benefit_bps"] = np.where(
    df["Approach"] == "1250%",
    0,
    np.round((df["RWA_Benefit_EURm"] / df["RWA_pre_EURm"]) * 10000, 1)
)

# =============================================================================
# 5. SUMMARY STATISTICS
# =============================================================================

print("=" * 65)
print("SECURITISATION PORTFOLIO — SUMMARY STATISTICS")
print("=" * 65)
print(f"Total transactions:              {N}")
print(f"Total notional (EUR m):          {df['Notional_EURm'].sum():,.1f}")
print(f"Total RWA pre-sec (EUR m):       {df['RWA_pre_EURm'].sum():,.1f}")
print(f"Total RWA post-sec (EUR m):      {df['RWA_post_EURm'].sum():,.1f}")
print(f"Total RWA benefit (EUR m):       {df['RWA_Benefit_EURm'].sum():,.1f}")
print(f"Avg capital benefit (bps):       {df['Capital_Benefit_bps'].mean():.1f}")
print(f"NPL securitisations:             {df['Is_NPL_Sec'].sum()} ({df['Is_NPL_Sec'].mean()*100:.1f}%)")
print()
print("By Approach:")
print(df.groupby("Approach")[["Notional_EURm","RWA_Benefit_EURm","Capital_Benefit_bps"]]
      .agg({"Notional_EURm":"sum","RWA_Benefit_EURm":"sum","Capital_Benefit_bps":"mean"})
      .round(1).to_string())
print()
print("By Tranche Type:")
print(df.groupby("Tranche_Type")[["Notional_EURm","Capital_Benefit_bps"]]
      .agg({"Notional_EURm":"sum","Capital_Benefit_bps":"mean"})
      .round(1).to_string())

# =============================================================================
# 6. VISUALISATION — SUPERVISORY DASHBOARD
# =============================================================================

plt.style.use("seaborn-v0_8-whitegrid")
COLORS = {
    "SEC-SA":    "#2166ac",
    "SEC-IRBA":  "#4dac26",
    "SEC-ERBA":  "#f4a582",
    "1250%":     "#d6604d",
    "Senior":       "#5aae61",
    "Mezzanine":    "#f7f7f7",
    "First Loss":   "#d73027",
    "NPL":          "#d73027",
    "Performing":   "#4dac26",
}

fig = plt.figure(figsize=(20, 14))
fig.suptitle("Securitisation Portfolio — Supervisory Dashboard",
             fontsize=16, fontweight="bold", y=0.98)
gs = GridSpec(2, 3, figure=fig, hspace=0.40, wspace=0.35)

# --- Panel 1: Notional by Approach (bar) ---
ax1 = fig.add_subplot(gs[0, 0])
approach_summary = df.groupby("Approach")["Notional_EURm"].sum().reindex(APPROACHES)
bars = ax1.bar(approach_summary.index,
               approach_summary.values / 1000,
               color=[COLORS[a] for a in approach_summary.index],
               edgecolor="white", linewidth=0.8)
ax1.set_title("Total Notional by Regulatory Approach", fontweight="bold", fontsize=10)
ax1.set_ylabel("Notional (EUR bn)")
ax1.set_xlabel("")
for bar, val in zip(bars, approach_summary.values / 1000):
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
             f"{val:.1f}", ha="center", va="bottom", fontsize=8)

# --- Panel 2: Capital Benefit Distribution (box) ---
ax2 = fig.add_subplot(gs[0, 1])
cb_data = [df[df["Approach"] == a]["Capital_Benefit_bps"].values for a in APPROACHES[:3]]
bp = ax2.boxplot(cb_data, labels=APPROACHES[:3], patch_artist=True,
                 medianprops=dict(color="black", linewidth=2))
for patch, approach_name in zip(bp["boxes"], APPROACHES[:3]):
    patch.set_facecolor(COLORS[approach_name])
    patch.set_alpha(0.7)
ax2.set_title("Capital Benefit Distribution by Approach\n(excl. 1250%)",
              fontweight="bold", fontsize=10)
ax2.set_ylabel("Capital Benefit (bps of RWA)")
ax2.set_xlabel("")

# --- Panel 3: Tranche Type Composition (donut) ---
ax3 = fig.add_subplot(gs[0, 2])
tranche_counts = df["Tranche_Type"].value_counts()
tranche_order  = ["Senior", "Mezzanine", "First Loss"]
tranche_counts = tranche_counts.reindex(
    [t for t in tranche_order if t in tranche_counts.index])
wedge_colors   = [COLORS[t] for t in tranche_counts.index]
wedges, texts, autotexts = ax3.pie(
    tranche_counts.values,
    labels=tranche_counts.index,
    colors=wedge_colors,
    autopct="%1.0f%%",
    startangle=90,
    wedgeprops=dict(width=0.55),
    textprops=dict(fontsize=9)
)
for at in autotexts:
    at.set_fontsize(8)
ax3.set_title("Tranche Type Distribution\n(CRR Art. 242)",
              fontweight="bold", fontsize=10)

# --- Panel 4: Attachment vs Detachment scatter (risk map) ---
ax4 = fig.add_subplot(gs[1, 0:2])
npl_color = df["Is_NPL_Sec"].map({True: COLORS["NPL"], False: COLORS["Performing"]})
sc = ax4.scatter(
    df["Attachment"] * 100,
    df["Detachment"] * 100,
    c=npl_color,
    s=df["Notional_EURm"] / 25,
    alpha=0.65,
    edgecolors="grey",
    linewidths=0.4
)
ax4.plot([0, 100], [0, 100], "k--", linewidth=0.8, alpha=0.3)
ax4.set_xlabel("Attachment Point (%)")
ax4.set_ylabel("Detachment Point (%)")
ax4.set_title("Transaction Risk Map — Attachment vs Detachment\n"
              "(bubble size = notional; red = NPL securitisation)",
              fontweight="bold", fontsize=10)
npl_patch  = mpatches.Patch(color=COLORS["NPL"],       label="NPL securitisation")
perf_patch = mpatches.Patch(color=COLORS["Performing"], label="Performing")
ax4.legend(handles=[npl_patch, perf_patch], fontsize=8, loc="upper left")

# --- Panel 5: RWA Benefit by Asset Class (horizontal bar) ---
ax5 = fig.add_subplot(gs[1, 2])
ac_summary = (df.groupby("Asset_Class")["RWA_Benefit_EURm"]
                .sum()
                .sort_values(ascending=True))
colors_ac  = sns.color_palette("Blues_d", len(ac_summary))
ax5.barh(ac_summary.index, ac_summary.values / 1000,
         color=colors_ac, edgecolor="white")
ax5.set_title("Total RWA Benefit by Asset Class",
              fontweight="bold", fontsize=10)
ax5.set_xlabel("RWA Benefit (EUR bn)")
for i, val in enumerate(ac_summary.values / 1000):
    ax5.text(val + 0.05, i, f"{val:.1f}", va="center", fontsize=8)

plt.savefig("/mnt/user-data/outputs/securitisation_dashboard.png",
            dpi=150, bbox_inches="tight")
plt.show()
print("\nDashboard saved to securitisation_dashboard.png")
