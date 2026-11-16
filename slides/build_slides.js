// Builds slides/crash_recovery.pptx (about 15 minutes).
// Numbers come from the notebooks' 2026-11-09 run; figures come from figures/.
// node 26, pptxgenjs 3.12.0
// Usage (from the project folder): NODE_PATH=<folder with pptxgenjs> node slides/build_slides.js [apply_theme.js path]
const pptxgen = require("pptxgenjs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const FIG = (name) => path.join(ROOT, "figures", name);
const OUT = path.join(ROOT, "slides", "crash_recovery.pptx");

const THEME = {
  name: "Crash Recovery",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1C2430", lt1: "FFFFFF", dk2: "3D4A5C", lt2: "EEF2F6",
    accent1: "2A78D6", accent2: "EB6834", accent3: "1BAF7A",
    accent4: "5B6B7F", accent5: "B4232C", accent6: "A3ADB8",
    hlink: "2A78D6", folHlink: "5B6B7F",
  },
};
const HEX = THEME.colors;
const CRASH = [
  { key: "2020", name: "COVID-19 (2020)", color: HEX.accent1 },
  { key: "2022", name: "Rate hikes (2022)", color: HEX.accent2 },
  { key: "2025", name: "Tariffs (2025)", color: HEX.accent3 },
];

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.author = "Raaj Banga";
pres.title = "Modeling Firm Recovery Across Three Market Crashes";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

// ---------- Layouts ----------
pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: HEX.dk1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.0, w: 11.7, h: 1.9,
        fontSize: 44, bold: true, color: C.background1, align: "left", valign: "bottom" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 4.1, w: 11.7, h: 1.6,
        fontSize: 20, color: C.background2, valign: "top" }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: HEX.lt1 },
  margin: [0.5, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.95,
        fontSize: 34, bold: true, color: C.text1, align: "left", valign: "middle" }, text: "" } },
    { text: { text: "Raaj Banga", options: { x: 0.6, y: 7.0, w: 4, h: 0.3, fontSize: 10,
        color: C.accent4, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: HEX.accent4, align: "right" },
});

// ---------- Small builders ----------
let objCount = 0;
const oname = (s) => `${s}-${++objCount}`;

function card(slide, x, y, w, h, fill = C.background2) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12,
    fill: { color: fill }, line: { type: "none" }, objectName: oname("card") });
}

function text(slide, t, opts) {
  slide.addText(t, { isTextBox: true, fontSize: 16, color: C.text1, valign: "top", margin: 0,
    objectName: oname("text"), ...opts });
}

function circleNum(slide, n, x, y, color) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: 0.5, h: 0.5, fill: { color }, line: { type: "none" },
    objectName: oname("dot") });
  text(slide, String(n), { x, y, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: C.background1,
    align: "center", valign: "middle" });
}

function bullets(items, size = 16) {
  return items.map((t, i) => ({ text: t, options: { bullet: { indent: 18 }, fontSize: size,
    paraSpaceAfter: 8, breakLine: i < items.length - 1 } }));
}

function content(title, section) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  return s;
}

// ---------- 1. Title ----------
pres.addSection({ title: "Intro" });
let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Intro" });
s.addText("Modeling Firm Recovery Across Three Market Crashes", { placeholder: "title" });
s.addText([
  { text: "Can pre-crash SEC filings predict which stocks recover, and does that hold when the next crash has a different cause?", options: { breakLine: true } },
  { text: " ", options: { fontSize: 10, breakLine: true } },
  { text: "Raaj Banga · November 2026", options: { fontSize: 16, color: C.accent6 } },
], { placeholder: "body" });
s.addNotes("Question: can a firm's financials before a crash tell us whether its stock comes back, and does a model built on one crash still work on the next one? Short answer: yes within a crash, no across crashes, and the reason is the interesting part.");

// ---------- 2. Three crashes ----------
s = content("Three crashes with three different causes", "Intro");
s.addImage({ path: FIG("sp500_crashes.png"), x: 0.6, y: 1.45, w: 7.4, h: 7.4 * 1109 / 1583,
  altText: "S&P 500 indexed to its pre-crash peak for the 2020, 2022 and 2025 crashes", objectName: "sp500" });
const crashCards = [
  ["COVID-19 (2020)", "Liquidity panic", "33 days to the trough · VIX 83 · yields fell"],
  ["Rate hikes (2022)", "Interest-rate shock", "282 days to the trough · VIX 36 · 10-year 1.6% → 3.9%"],
  ["Tariffs (2025)", "Trade-policy shock", "48 days to the trough · VIX 52 · yields stayed near 4.3%"],
];
crashCards.forEach(([name, cause, facts], i) => {
  const y = 1.55 + i * 1.75;
  card(s, 8.4, y, 4.3, 1.5);
  s.addShape(pres.shapes.OVAL, { x: 8.65, y: y + 0.25, w: 0.28, h: 0.28, fill: { color: CRASH[i].color },
    line: { type: "none" }, objectName: oname("dot") });
  text(s, name, { x: 9.05, y: y + 0.2, w: 3.5, h: 0.4, fontSize: 18, bold: true });
  text(s, cause, { x: 9.05, y: y + 0.6, w: 3.5, h: 0.35, fontSize: 15, italic: true, color: C.text2 });
  text(s, facts, { x: 9.05, y: y + 0.95, w: 3.5, h: 0.45, fontSize: 12, color: C.accent4 });
});
s.addNotes("The three crashes behave very differently. 2020 was a fast liquidity panic and a fast rebound. 2022 was a slow grind driven by rising rates; the market took two years to get back. 2025 was short and shallow. If a signal predicts recovery in all three, it's likely real. If it only works in one, it's tied to that crash's cause.");

// ---------- 3. Setup ----------
s = content("Train on one crash, test on another", "Intro");
text(s, bullets([
  "One row per firm per crash: 10,513 rows, 4,657 firms",
  "Features: 12 from SEC filings filed before the peak (liquidity, leverage, profitability, growth, size) and 4 from prices (market value, volatility, momentum, beta)",
  "Main label: back to the pre-crash price within 12 months of the market trough",
  "Second label: beat the S&P 500 (SPY) over the same window",
  "Metric: AUC (0.5 = coin flip), since base rates differ a lot by crash",
], 16), { x: 0.6, y: 1.6, w: 5.9, h: 4.8 });
// 3x3 design grid
const gx = 7.3, gy = 2.05, cw = 1.75, ch = 1.15;
text(s, "Tested on →", { x: gx + cw * 0.5, y: 1.45, w: cw * 3, h: 0.35, fontSize: 13, color: C.accent4, align: "center" });
text(s, "Trained on ↓", { x: gx - 1.05, y: gy - 0.48, w: 1.2, h: 0.35, fontSize: 13, color: C.accent4 });
CRASH.forEach((c, j) => text(s, c.key, { x: gx + 0.5 + j * cw, y: gy - 0.38, w: cw, h: 0.3, fontSize: 14, bold: true, align: "center" }));
CRASH.forEach((r, i) => {
  text(s, r.key, { x: gx - 0.55, y: gy + i * ch, w: 0.95, h: ch, fontSize: 14, bold: true, valign: "middle" });
  CRASH.forEach((c, j) => {
    const kind = i === j ? "within\n(cross-val.)" : j > i ? "forward" : "backward";
    const fill = i === j ? C.text1 : j > i ? C.accent1 : C.background2;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: gx + 0.5 + j * cw + 0.05, y: gy + i * ch + 0.05,
      w: cw - 0.1, h: ch - 0.1, rectRadius: 0.08, fill: { color: fill }, line: { type: "none" }, objectName: oname("cell") });
    text(s, kind, { x: gx + 0.5 + j * cw, y: gy + i * ch, w: cw, h: ch, fontSize: 14, align: "center", valign: "middle",
      color: i === j || j > i ? C.background1 : C.text1 });
  });
});
text(s, "Forward pairs are what real use looks like: train on the past, predict the next crash. Firms in several crashes stay in one fold.",
  { x: gx - 0.55, y: gy + 3 * ch + 0.2, w: 6.0, h: 0.8, fontSize: 13, color: C.text2 });
s.addNotes("Each firm in each crash is one row. Features use only SEC facts filed before the market peak, so nothing from after the crash leaks in. The main test is the grid on the right: the diagonal is ordinary cross-validation inside one crash; the off-diagonal cells train on one crash and test on another. 71% of rows are firms that appear in all three crashes, so folds and bootstrap resamples keep each firm together.");

// ---------- 4. Data ----------
pres.addSection({ title: "Data" });
s = content("Every SEC filer, including firms that later failed", "Data");
const steps = [
  ["15,291", "firm-crash rows", "SEC XBRL filers, not today's listings"],
  ["13,392", "tickers matched", "checked against the firm's identity at the peak"],
  ["12,931", "verified prices", "Yahoo + Tiingo, checked against SEC fails prices"],
  ["10,513", "final rows", "≥ $1, ≥ $10M, actively traded, common stock"],
];
steps.forEach(([n, lab, note], i) => {
  const x = 0.6 + i * 3.1;
  card(s, x, 1.6, 2.8, 2.2);
  text(s, n, { x: x + 0.25, y: 1.8, w: 2.4, h: 0.75, fontSize: 36, bold: true, fontFace: THEME.headFontFace });
  text(s, lab, { x: x + 0.25, y: 2.55, w: 2.4, h: 0.35, fontSize: 16, bold: true, color: C.text2 });
  text(s, note, { x: x + 0.25, y: 2.95, w: 2.35, h: 0.75, fontSize: 13, color: C.accent4 });
  if (i < 3) text(s, "→", { x: x + 2.8, y: 2.35, w: 0.3, h: 0.5, fontSize: 22, color: C.accent6, align: "center" });
});
const guards = [
  ["Survivorship bias", "Dead firms come from SEC records and Tiingo, not today's ticker lists."],
  ["Look-ahead bias", "Only facts filed before the peak; later restatements can't leak in."],
  ["Wrong-company prices", "Reused tickers caught by issuer code and name at the peak (Ambac's old ticker now belongs to another firm)."],
];
guards.forEach(([h, b], i) => {
  const x = 0.6 + i * 4.15;
  circleNum(s, i + 1, x, 4.35, C.text1);
  text(s, h, { x: x + 0.65, y: 4.38, w: 3.3, h: 0.45, fontSize: 18, bold: true });
  text(s, b, { x: x + 0.65, y: 4.85, w: 3.3, h: 1.3, fontSize: 14, color: C.text2 });
});
text(s, "34 automated checks on the final table; flagged rows reviewed by hand.",
  { x: 0.6, y: 6.35, w: 12, h: 0.35, fontSize: 13, italic: true, color: C.accent4 });
s.addNotes("Most of the project time went into data. Starting from SEC filers instead of today's listings keeps firms that later went bankrupt. Prices from Yahoo for listed firms and Tiingo for firms that left the market, each checked against the SEC's own fails-to-deliver prices. An audit found tickers that had been reused by other companies, so the ticker match now checks the issuer at the time of the crash. Filters: at least a dollar, at least 10 million in market value, actively traded.");

// ---------- 5. Base rates ----------
s = content("How many firms recovered depended on the crash", "Data");
s.addImage({ path: FIG("km_by_crash.png"), x: 0.6, y: 1.45, w: 8.2, h: 8.2 * 869 / 1738,
  altText: "Share of firms back at their pre-crash price by days after the trough, per crash", objectName: "km" });
const rates = [["76%", "247"], ["43%", "539"], ["70%", "142"]];
text(s, "Back within 12 months", { x: 9.2, y: 1.5, w: 3.5, h: 0.35, fontSize: 14, color: C.accent4 });
rates.forEach(([r, d], i) => {
  const y = 1.95 + i * 1.5;
  card(s, 9.2, y, 3.5, 1.3);
  s.addShape(pres.shapes.OVAL, { x: 9.4, y: y + 0.2, w: 0.25, h: 0.25, fill: { color: CRASH[i].color },
    line: { type: "none" }, objectName: oname("dot") });
  text(s, CRASH[i].name, { x: 9.75, y: y + 0.15, w: 2.8, h: 0.35, fontSize: 14, bold: true, color: C.text2 });
  text(s, r, { x: 9.4, y: y + 0.5, w: 1.5, h: 0.7, fontSize: 34, bold: true, fontFace: THEME.headFontFace });
  text(s, `median ${d} days to recover`, { x: 10.9, y: y + 0.62, w: 1.75, h: 0.55, fontSize: 12, color: C.accent4 });
});
text(s, "Failure was rare (0.4–0.8% within 12 months), so exits barely change the curves.",
  { x: 0.6, y: 5.75, w: 8.2, h: 0.5, fontSize: 13, italic: true, color: C.accent4 });
s.addNotes("Kaplan-Meier curves: share of firms back at their pre-crash price by days after the market trough. 2020 firms recovered steadily; in 2022 half the firms never got back within 18 months. Base rates differ this much, so I compare models with AUC rather than accuracy. Always guessing 'recovers' would already be 76% accurate in 2020.");

// ---------- 6. Methods ----------
pres.addSection({ title: "Results" });
s = content("Five questions, five kinds of method", "Results");
const methods = [
  ["Prediction", "Do fundamentals beat a sector-and-size baseline?", "Logistic regression, random forest, LightGBM"],
  ["Transfer", "How much accuracy is lost on a new crash?", "Cross-crash tests, DeLong tests, firm-grouped bootstrap CIs"],
  ["Archetypes", "Do kinds of firms recover differently?", "k-means, HDBSCAN, FP-Growth rules"],
  ["Exceptions", "Which firms beat or broke the odds?", "Isolation Forest, LOF"],
  ["Timing", "How long does recovery take?", "Kaplan-Meier, Cox proportional hazards"],
];
methods.forEach(([h, q, m], i) => {
  const y = 1.55 + i * 1.03;
  card(s, 0.6, y, 12.1, 0.88);
  circleNum(s, i + 1, 0.8, y + 0.19, i < 2 ? C.text1 : C.accent4);
  text(s, h, { x: 1.5, y: y + 0.22, w: 2.0, h: 0.45, fontSize: 18, bold: true });
  text(s, q, { x: 3.5, y: y + 0.24, w: 4.6, h: 0.45, fontSize: 15, color: C.text2 });
  text(s, m, { x: 8.2, y: y + 0.24, w: 4.4, h: 0.45, fontSize: 15, color: C.accent4 });
});
s.addNotes("The first two are the core: prediction and transfer. Every model is compared with a simple baseline that only knows sector and size. Significance uses DeLong tests with a Holm correction, and confidence intervals resample whole firms. The other three give context: are there kinds of firms, which firms surprised the model, and how fast recovery happened.");

// ---------- 7. Within a crash ----------
s = content("Within one crash, fundamentals beat the baseline", "Results");
s.addImage({ path: FIG("within_auc.png"), x: 0.6, y: 1.6, w: 7.9, h: 7.9 * 781 / 1377,
  altText: "AUC of the baseline and LightGBM within each crash, recovered within 12 months", objectName: "within-auc" });
text(s, "AUC, recovered within 12 months; 5-fold cross-validation with each firm kept in one fold.",
  { x: 0.6, y: 6.2, w: 7.9, h: 0.4, fontSize: 12, color: C.accent4 });
const within = [
  ["+0.02 to +0.07", "AUC over the baseline, every crash and both labels"],
  ["16 of 18", "model-vs-baseline gains significant after Holm"],
  ["0.71–0.73", "LightGBM AUC for beating SPY (2020, 2022)"],
];
within.forEach(([n, l], i) => {
  const y = 1.6 + i * 1.65;
  card(s, 8.9, y, 3.8, 1.4);
  text(s, n, { x: 9.15, y: y + 0.18, w: 3.4, h: 0.6, fontSize: 28, bold: true, fontFace: THEME.headFontFace });
  text(s, l, { x: 9.15, y: y + 0.78, w: 3.4, h: 0.55, fontSize: 13, color: C.text2 });
});
s.addNotes("Inside one crash the signal is real. LightGBM beats the sector-and-size baseline in every crash, for both labels, and 16 of 18 gains survive the Holm correction. Random forest scores about the same. AUCs around 0.7 are reasonable for predicting stock outcomes. Note: models score lower on plain accuracy than always guessing 'recovers' in 2020, which is why AUC is the metric.");

// ---------- 8. Across crashes ----------
s = content("Across crashes, the same models fall below the baseline", "Results");
const cellFill = (v, diag) => diag ? HEX.dk1 : v < 0.5 ? "F4D3CD" : v < 0.55 ? HEX.lt2 : "CFE0F5";
const tm = [[0.678, 0.457, 0.517], [0.456, 0.703, 0.602], [0.456, 0.579, 0.674], [0.422, 0.518, 0.546]];
const rowNames = ["2020", "2022", "2025", "Other two"];
const hdr = (t) => ({ text: t, options: { bold: true, fontSize: 15, color: C.text2, align: "center", valign: "middle", fill: { color: HEX.lt1 } } });
const rows = [[hdr("Trained on ↓  Tested on →"), hdr("2020"), hdr("2022"), hdr("2025")]];
tm.forEach((r, i) => rows.push([
  { text: rowNames[i], options: { bold: true, fontSize: 15, align: "center", valign: "middle", color: C.text1, fill: { color: HEX.lt1 } } },
  ...r.map((v, j) => ({ text: v.toFixed(2) + (i === j ? "  (within)" : ""), options: { fontSize: 18, align: "center", valign: "middle",
    bold: i === j, color: i === j ? C.background1 : C.text1, fill: { color: cellFill(v, i === j) } } })),
]));
s.addTable(rows, { x: 0.6, y: 1.6, w: 7.6, colW: [2.5, 1.7, 1.7, 1.7], rowH: 0.78, border: { type: "solid", pt: 2, color: HEX.lt1 },
  fontFace: THEME.bodyFontFace, objectName: "transfer-table" });
text(s, "LightGBM AUC, recovered within 12 months. Red: below chance. Blue: above 0.55.",
  { x: 0.6, y: 5.65, w: 7.6, h: 0.4, fontSize: 12, color: C.accent4 });
card(s, 8.7, 1.6, 4.0, 2.05);
text(s, "−0.055", { x: 8.95, y: 1.78, w: 3.5, h: 0.75, fontSize: 40, bold: true, color: C.accent5, fontFace: THEME.headFontFace });
text(s, "AUC vs the baseline across crashes, pooled (95% CI −0.066 to −0.044)", { x: 8.95, y: 2.6, w: 3.5, h: 0.9, fontSize: 13, color: C.text2 });
card(s, 8.7, 3.9, 4.0, 2.05);
text(s, "≈ 0.51", { x: 8.95, y: 4.08, w: 3.5, h: 0.75, fontSize: 40, bold: true, fontFace: THEME.headFontFace });
text(s, "mean cross-crash AUC, against about 0.69 within a crash", { x: 8.95, y: 4.9, w: 3.5, h: 0.9, fontSize: 13, color: C.text2 });
s.addNotes("This is the main result. Off the diagonal, AUC drops to between 0.42 and 0.60. Anything involving 2020 is at or below chance. 2022 and 2025 transfer to each other a little, around 0.6. Worse: a model trained on past crashes does worse than the simple baseline. A model learned from the last crash isn't just weaker on the next one; it's misleading. Beating SPY looks the same.");

// ---------- 9. Why ----------
s = content("Why: the same trait helped in one crash and hurt in the next", "Results");
s.addImage({ path: FIG("volatility_flip.png"), x: 1.17, y: 1.45, w: 11.0, h: 11.0 * 791 / 1987,
  altText: "Recovery and beat-SPY rates by pre-crash volatility third, per crash", objectName: "flip" });
const why = [
  ["2020: liquidity panic", "Risky stocks fell hardest and bounced back hardest. High-volatility firms beat SPY 59% of the time vs 30% for low."],
  ["2022 and 2025: rate and trade shocks", "Investors moved to safety. High-volatility firms recovered least (27% vs 56% in 2022)."],
];
why.forEach(([h, b], i) => {
  const x = 0.6 + i * 6.15;
  text(s, h, { x, y: 5.95, w: 5.9, h: 0.35, fontSize: 16, bold: true });
  text(s, b, { x, y: 6.3, w: 5.9, h: 0.6, fontSize: 13, color: C.text2 });
});
s.addNotes("Here is the reason. Split firms into thirds by how volatile their stock was before the crash. In 2020 the most volatile third recovered and beat the market most. In 2022 and 2025 it's the opposite. A model trained on 2020 learns 'volatile is good' and applies it in 2022, where volatile is bad. Volatility is the top SHAP feature in 2022 and 2025, with the sign reversed from 2020.");

// ---------- 10. Signals ----------
s = content("Almost no signal holds in all three crashes", "Results");
const sig = [
  ["Universal", C.text1, ["None by our rule (top 5 everywhere, same sign)", "Closest: firm size (rank 7 in 2020)", "Survival model: only momentum is significant and same-signed in all three"]],
  ["Crash-specific", C.accent4, ["2020: cash to assets, market value", "2022: asset growth, momentum", "2025: operating margin"]],
  ["Reversed", C.accent5, ["Volatility: + in 2020, top negative in 2022 and 2025", "Cox model: return on assets, size, beta and financials flip sign"]],
];
sig.forEach(([h, col, items], i) => {
  const x = 0.6 + i * 4.1;
  card(s, x, 1.6, 3.8, 3.1);
  circleNum(s, i + 1, x + 0.25, 1.8, col);
  text(s, h, { x: x + 0.9, y: 1.83, w: 2.7, h: 0.45, fontSize: 20, bold: true });
  text(s, bullets(items, 15), { x: x + 0.25, y: 2.55, w: 3.35, h: 2.8, color: C.text2 });
});
text(s, "Feature importance ranks agree only partly between crashes (Spearman 0.38 to 0.62 for recovery).",
  { x: 0.6, y: 5.05, w: 12.1, h: 0.4, fontSize: 14, italic: true, color: C.accent4 });
s.addNotes("The novelty question was: which signals are universal and which are crash-specific. The answer is that almost nothing is universal. Each crash has its own leading signals, and some flip sign. Even the importance rankings only partly agree between crashes, and 2020 vs 2025 agree least.");

// ---------- 11. Archetypes ----------
s = content("The kind of firm that recovers best changes with the crash", "Results");
s.addImage({ path: FIG("archetype_recovery.png"), x: 0.6, y: 1.5, w: 7.8, h: 7.8 * 981 / 1508,
  altText: "Share recovered within 12 months by archetype and crash", objectName: "archetype-recovery" });
text(s, bullets([
  "k-means on within-crash percentiles finds 3 broad archetypes (k = 3, stable across seeds)",
  "Profitable firms led in 2020; large, calm firms led in 2022 and 2025",
  "Loss-makers fell furthest behind in 2022 (27%)",
  "Firms form a continuum, not tight groups (HDBSCAN: 77% noise)",
  "Few association rules hold in all three crashes",
], 15), { x: 9.0, y: 1.7, w: 3.7, h: 5.0, color: C.text2 });
s.addNotes("Clustering gives the same story from a different angle. The three archetypes are broad tendencies, since the firms form a continuum. Which archetype recovers best depends on the crash. Chi-square tests: recovery differs by archetype in every crash, and each archetype's recovery differs across crashes, while the mix of archetypes barely changes.");

// ---------- 12. Robustness ----------
s = content("The gap survives every check we tried", "Results");
const rob = [
  ["Check", "Within-crash AUC", "Cross-crash AUC"],
  ["Main result (LightGBM)", "≈ 0.69", "≈ 0.51"],
  ["Drop 377 firms acquired before 12 months", "0.690", "0.510"],
  ["Beta-adjusted label (beat beta × SPY)", "0.702", "0.480"],
  ["Within-crash percentile features", "—", "−0.004 change"],
  ["Firms seen in training vs new firms", "—", "same pattern"],
  ["Yahoo prices only", "within ±0.04", "≈ 0.5"],
  ["Peak-day close as the pre-crash price", "same pattern", "same pattern"],
];
s.addTable(rob.map((r, i) => r.map((t, j) => ({ text: t, options: { fontSize: 15, bold: i === 0, color: i === 0 ? C.background1 : C.text1,
  fill: { color: i === 0 ? HEX.dk1 : i % 2 ? HEX.lt2 : HEX.lt1 }, align: j === 0 ? "left" : "center", valign: "middle" } }))),
  { x: 0.6, y: 1.6, w: 12.1, colW: [6.1, 3.0, 3.0], rowH: 0.56, margin: [0, 0.15, 0, 0.15], border: { type: "none" },
    fontFace: THEME.bodyFontFace, objectName: "robustness-table" });
text(s, "Even the most similar pair, 2022 → 2025, doesn't beat the baseline (0.602 vs 0.618, not significant).",
  { x: 0.6, y: 6.25, w: 12.1, h: 0.4, fontSize: 14, italic: true, color: C.accent4 });
s.addNotes("To make sure the transfer gap isn't an artifact: dropping early acquisitions, changing the label to adjust for beta, using percentiles instead of raw values, separating repeat firms, and using only one price source all give the same picture. The forward test from 2022 to 2025 is the realistic use case, and even that doesn't beat the baseline.");

// ---------- 13. Limits ----------
pres.addSection({ title: "Wrap-up" });
s = content("Limits", "Wrap-up");
const lim = [
  ["Only three crashes", "Too few to model crash type directly; the crash-type story is an interpretation."],
  ["Missing prices", "3.4% of matched rows have no checked price. They're smaller and fail more often."],
  ["Identity checks", "Tickers checked against the firm at the peak for 92.5% of rows; the rest had no SEC fails record."],
  ["Mixed price sources", "Yahoo for listed firms, Tiingo for firms that left; results hold with Yahoo only."],
  ["Model assumptions", "Weak cluster structure; proportional hazards fail for some features."],
  ["Sector codes", "SEC gives current SIC codes, not the codes in use at each crash."],
];
lim.forEach(([h, b], i) => {
  const col = i % 2, row = Math.floor(i / 2);
  const x = 0.6 + col * 6.15, y = 1.6 + row * 1.6;
  card(s, x, y, 5.95, 1.4);
  text(s, h, { x: x + 0.3, y: y + 0.2, w: 5.4, h: 0.4, fontSize: 18, bold: true });
  text(s, b, { x: x + 0.3, y: y + 0.65, w: 5.4, h: 0.65, fontSize: 14, color: C.text2 });
});
s.addNotes("The biggest limit is that there are only three crashes, so I can show signals change with crash type but can't fit a model of crash type. Data limits are small and all go in the same direction as survivorship: the firms without prices are smaller and fail more.");

// ---------- 14. Takeaway ----------
s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Wrap-up" });
s.addText("What predicts recovery depends on what caused the crash", { placeholder: "title" });
s.addText([
  { text: "Within a crash, fundamentals predict recovery (AUC ≈ 0.69).", options: { bullet: { indent: 20 }, breakLine: true } },
  { text: "Across crashes, models fall below a simple baseline (AUC ≈ 0.51).", options: { bullet: { indent: 20 }, breakLine: true } },
  { text: "Don't trust a “crash-resilient” stock screen built on a past crash unless that crash had a similar cause.", options: { bullet: { indent: 20 } } },
], { placeholder: "body" });
s.addNotes("To sum up: the signal is real within a crash, but it's tied to the cause of that crash. Future work: more crashes, so crash type itself could be a feature, and adding pre-crash macro context to choose which past crash to learn from. Questions?");

// ---------- Write ----------
(async () => {
  await pres.writeFile({ fileName: OUT });
  const themeJs = process.argv[2];
  if (themeJs) {
    const { applyTheme } = require(themeJs);
    await applyTheme(OUT, THEME);
  }
  console.log("wrote", OUT);
})();
