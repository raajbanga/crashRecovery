// Builds slides/crash_recovery.pptx (about 13 minutes plus questions).
// The deck explains how the data was built and how the models were tested; numbers come from the
// notebooks' 2026-11-09 run, and figures from figures/ (plot_method_figures.py draws the two
// method figures).
//
// The speaker script is slides/script.md (git-ignored); the deck itself carries no notes.
// On macOS the build also exports a PDF of the deck through Keynote.
//
// node 26, pptxgenjs 3.12.0. The look follows the project page in dark mode. Fonts: Newsreader
// (the page's serif) for headings, as the static "Newsreader Display" instance, and Helvetica Neue
// for body text. Figures come from figures/slides/ (scripts/plot_slide_figures.py).
// From the project folder: NODE_PATH=<folder with pptxgenjs> node slides/build_slides.js
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..");
const FIG = (name) => path.join(ROOT, "figures", "slides", name);
const OUT = path.join(ROOT, "slides", "crash_recovery.pptx");
const COURSE = ""; // the course copy of this repo sets this to the course name

// ---------- Palette: the project page's dark-mode tokens (docs/index.html) ----------
const K = {
  bg: "0F1419", // --plane
  plane: "161C22", // --surface: cards
  plane2: "1D252D", // raised fills, table headers
  ink: "E9EDF1",
  ink2: "AEB8C2",
  muted: "7F8A95",
  rule: "2A323A",
  axis: "3A434C",
  darkText: "AEB8C2",
  dark: "1C5CAB", // emphasis fill (--pos-2)
  c0: "3987E5", // COVID-19 (2020)
  c1: "D95926", // Rate hikes (2022)
  c2: "199E70", // Tariffs (2025)
  blue: "6DA7EC", // --focus, blue text
  red: "F0A1A0",
  redFill: "4A2223", // --neg-1
  blueFill: "1B3556", // --pos-1
  green: "3FC79A",
  greenFill: "123329",
};
const HEAD = "Newsreader Display";
const BODY = "Helvetica Neue";
const CRASH = [
  { key: "2020", name: "COVID-19 (2020)", color: K.c0, text: K.c0 },
  { key: "2022", name: "Rate hikes (2022)", color: K.c1, text: K.c1 },
  { key: "2025", name: "Tariffs (2025)", color: K.c2, text: K.c2 },
];

function buildDeck() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
  pres.author = "Raaj Banga";
  pres.title = "Modeling Firm Recovery Across Three Market Crashes";
  pres.theme = { headFontFace: HEAD, bodyFontFace: BODY };

  pres.defineSlideMaster({
    title: "DARK",
    background: { color: K.bg },
    objects: [],
  });
  pres.defineSlideMaster({
    title: "CONTENT",
    background: { color: K.bg },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.6, w: 12.1, h: 0.74, fontFace: HEAD,
          fontSize: 32, bold: false, color: K.ink, align: "left", valign: "middle", margin: 0 }, text: "" } },
      { line: { x: 0.6, y: 6.94, w: 12.13, h: 0, line: { color: K.rule, width: 0.75 } } },
      { text: { text: "Crash Recovery", options: { x: 0.6, y: 7.02, w: 6, h: 0.28,
          fontSize: 11, bold: true, color: K.ink2, fontFace: HEAD, margin: 0 } } },
    ],
    slideNumber: { x: 12.2, y: 7.02, w: 0.5, h: 0.28, fontSize: 10, color: K.muted, fontFace: BODY, align: "right" },
  });

  let n = 0;
  const oname = (s) => `${s}-${++n}`;
  const T = (slide, t, o) => slide.addText(t, { isTextBox: true, fontFace: BODY, fontSize: 15, color: K.ink,
    valign: "top", margin: 0, objectName: oname("text"), ...o, ...(o.fontFace === HEAD ? { bold: false } : {}) });
  // the page's crash motif: a 4px rule in the crash's color on top of a block
  const topRule = (slide, x, y, w, color) => slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h: 0.055,
    fill: { color }, line: { type: "none" }, objectName: oname("rule") });
  const box = (slide, x, y, w, h, o = {}) => slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h,
    rectRadius: 0.08, fill: { color: o.fill || K.plane }, line: o.line ? { color: o.line, width: o.lineW || 1.25 } : { type: "none" },
    objectName: oname("box") });
  const dot = (slide, x, y, d, color) => slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color },
    line: { type: "none" }, objectName: oname("dot") });
  const num = (slide, k, x, y, color = K.ink) => {
    dot(slide, x, y, 0.42, color === K.ink ? K.blueFill : color);
    T(slide, String(k), { x, y, w: 0.42, h: 0.42, fontSize: 16, color: K.blue, align: "center", valign: "middle", fontFace: HEAD });
  };
  const arrow = (slide, x1, y1, x2, y2, color = K.axis) => slide.addShape(pres.shapes.LINE, {
    x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.max(Math.abs(x2 - x1), 0.001), h: Math.max(Math.abs(y2 - y1), 0.001),
    flipH: x2 < x1, flipV: y2 < y1, line: { color, width: 1.5, endArrowType: "triangle" }, objectName: oname("arrow") });
  const bullets = (items, o = {}) => items.map((t, i) => {
    const runs = Array.isArray(t) ? t : [{ text: t }];
    return runs.map((r, j) => ({ text: r.text, options: { ...(j === 0 ? { bullet: { indent: 16 } } : {}),
      fontSize: o.size || 15, color: K.ink2, paraSpaceAfter: o.space ?? 7, bold: r.bold, color: r.color || K.ink2,
      breakLine: j === runs.length - 1 && i < items.length - 1 } }));
  }).flat();
  const pngSize = (f) => { const b = fs.readFileSync(f); return [b.readUInt32BE(16), b.readUInt32BE(20)]; };
  const img = (slide, file, x, y, w, alt) => { const [pw, ph] = pngSize(FIG(file));
    return slide.addImage({ path: FIG(file), x, y, w, h: (w * ph) / pw, altText: alt, objectName: oname("figure") }); };

  const content = (section, kicker, title, sub) => {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
    T(s, kicker, { x: 0.6, y: 0.34, w: 9, h: 0.26, fontSize: 11.5, color: K.blue, bold: true, charSpacing: 1.5 });
    s.addText(title, { placeholder: "title" });
    if (sub) T(s, sub, { x: 0.6, y: 1.36, w: 12.1, h: 0.4, fontSize: 15, color: K.ink2 });
    return s;
  };

  // ---------- 1. Title ----------
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "DARK", sectionTitle: "Introduction" });
  T(s, "Crash Recovery", { x: 0.8, y: 0.7, w: 4, h: 0.4, fontFace: HEAD, fontSize: 18, color: K.ink2 });
  T(s, "Modeling Firm Recovery Across Three Market Crashes", { x: 0.8, y: 1.45, w: 7.3, h: 2.3, fontFace: HEAD,
    fontSize: 46, color: K.ink, valign: "bottom", lineSpacingMultiple: 0.92 });
  T(s, "How the data was built, what was measured, and how the models were tested", { x: 0.8, y: 3.95, w: 7.0, h: 0.8,
    fontSize: 18, color: K.darkText });
  T(s, [
    { text: "Raaj Banga", options: { bold: true, color: K.ink, breakLine: true } },
    { text: ["Western Kentucky University", COURSE, "November 2026"].filter(Boolean).join(" · "), options: { color: K.darkText } },
  ], { x: 0.8, y: 5.15, w: 7.0, h: 0.7, fontSize: 15 });
  const titleCrashes = [
    ["−34% in 33 days", "index back 5 months after the trough"],
    ["−25% in 282 days", "back 15 months after the trough"],
    ["−19% in 48 days", "back under 3 months after the trough"],
  ];
  CRASH.forEach((c, i) => {
    const y = 1.6 + i * 1.38;
    topRule(s, 8.6, y, 4.1, c.color);
    T(s, c.name.replace(/[()]/g, ""), { x: 8.6, y: y + 0.17, w: 4.1, h: 0.4, fontSize: 21, fontFace: HEAD });
    T(s, titleCrashes[i][0], { x: 8.6, y: y + 0.6, w: 4.1, h: 0.28, fontSize: 13, color: K.ink2 });
    T(s, titleCrashes[i][1], { x: 8.6, y: y + 0.87, w: 4.1, h: 0.28, fontSize: 11.5, color: K.muted });
  });
  T(s, "10,513 firm-crash rows · 4,657 firms · 16 features", { x: 8.6, y: 5.85, w: 4.1, h: 0.3, fontSize: 12, color: K.muted });

  // ---------- 2. The question ----------
  s = content("Introduction", "INTRODUCTION", "One question, three crashes",
    "Do pre-crash SEC filings predict which stocks recover, and does that still hold when the next crash has a different cause?");
  img(s, "sp500_crashes.png", 0.6, 1.95, 6.7, "S&P 500 indexed to its pre-crash peak for the 2020, 2022 and 2025 crashes");
  const why3 = [
    ["Liquidity panic", "Fast fall, fast rebound. VIX hit 83; yields fell."],
    ["Interest-rate shock", "A slow grind: 10-year yield 1.6% → 3.9%. The index needed 15 months to get back."],
    ["Trade-policy shock", "Short and shallow (under 20%, so a “shock,” not a bear market)."],
  ];
  CRASH.forEach((c, i) => {
    const y = 1.98 + i * 1.5;
    topRule(s, 7.7, y, 5.0, c.color);
    T(s, c.name.replace(/[()]/g, ""), { x: 7.7, y: y + 0.14, w: 2.6, h: 0.36, fontSize: 19, fontFace: HEAD });
    T(s, why3[i][0], { x: 10.2, y: y + 0.17, w: 2.5, h: 0.32, fontSize: 13, color: K.ink2, align: "right" });
    T(s, why3[i][1], { x: 7.7, y: y + 0.6, w: 5.0, h: 0.6, fontSize: 12.5, color: K.ink2 });
  });
  T(s, "Different causes are the point: a signal that holds in all three is likely real; one that works once may only reflect that crash.",
    { x: 7.7, y: 6.5, w: 5.0, h: 0.45, fontSize: 12, italic: true, color: K.ink2 });

  // ---------- 3. Pipeline ----------
  pres.addSection({ title: "Data" });
  s = content("Data", "DATA · PIPELINE", "From raw filings to one table",
    "Five numbered scripts build one row per firm per crash; four notebooks analyze it.");
  T(s, "SOURCES", { x: 0.6, y: 1.95, w: 3.3, h: 0.25, fontSize: 11, bold: true, color: K.muted, charSpacing: 1 });
  const sources = [
    ["SEC company facts", "XBRL financials for 20,547 filers"],
    ["SEC filing histories", "10-Ks, Form 25 / 15, 8-K items"],
    ["SEC fails-to-deliver files", "185 files: ticker, issuer code, price"],
    ["Yahoo + Tiingo", "daily prices; Tiingo for firms that left"],
    ["FRED", "S&P 500, VIX, 10-year yield (context only)"],
  ];
  sources.forEach(([h, b], i) => {
    const y = 2.28 + i * 0.9;
    box(s, 0.6, y, 3.3, 0.78);
    T(s, h, { x: 0.78, y: y + 0.1, w: 3.0, h: 0.3, fontSize: 14, bold: true });
    T(s, b, { x: 0.78, y: y + 0.41, w: 3.05, h: 0.3, fontSize: 11.5, color: K.muted });
  });
  T(s, "SCRIPTS", { x: 4.5, y: 1.95, w: 4.4, h: 0.25, fontSize: 11, bold: true, color: K.muted, charSpacing: 1 });
  const steps = [
    ["03", "Universe", "SEC filers before each peak", "15,291"],
    ["04", "Tickers", "matched; identity checked", "13,392"],
    ["05", "Price check", "Yahoo / Tiingo vs SEC fails prices", "12,931"],
    ["06", "Labels", "clean prices, filter, label", "10,559"],
    ["07", "Features", "point-in-time SEC facts + prices", "10,513"],
  ];
  steps.forEach(([k, h, b, cnt], i) => {
    const y = 2.28 + i * 0.9;
    box(s, 4.5, y, 4.4, 0.78, { fill: K.bg, line: K.rule });
    T(s, k, { x: 4.65, y: y + 0.12, w: 0.5, h: 0.5, fontSize: 18, bold: true, color: K.blue, fontFace: HEAD, valign: "middle" });
    T(s, h, { x: 5.2, y: y + 0.1, w: 2.3, h: 0.3, fontSize: 14, bold: true });
    T(s, b, { x: 5.2, y: y + 0.41, w: 2.6, h: 0.3, fontSize: 11.5, color: K.muted });
    T(s, cnt, { x: 7.6, y: y + 0.12, w: 1.15, h: 0.5, fontSize: 16, bold: true, align: "right", valign: "middle", fontFace: HEAD });
    if (i < 4) arrow(s, 6.7, y + 0.78, 6.7, y + 0.9, K.axis);
  });
  T(s, "rows left after each step", { x: 6.9, y: 6.82, w: 2.0, h: 0.2, fontSize: 10, color: K.muted, align: "right" });
  arrow(s, 3.98, 4.06, 4.42, 4.06);
  arrow(s, 8.98, 4.06, 9.42, 4.06);
  T(s, "ANALYSIS", { x: 9.5, y: 1.95, w: 3.2, h: 0.25, fontSize: 11, bold: true, color: K.muted, charSpacing: 1 });
  box(s, 9.5, 2.28, 3.2, 1.05, { fill: K.dark });
  T(s, "firm_crash.parquet", { x: 9.68, y: 2.4, w: 2.9, h: 0.32, fontSize: 14, bold: true, color: K.ink });
  T(s, "10,513 rows × 70 columns, 34 automated checks", { x: 9.68, y: 2.73, w: 2.9, h: 0.5, fontSize: 11.5, color: K.darkText });
  const nbs = [["01", "explore"], ["02", "classification"], ["03", "patterns"], ["04", "survival"]];
  nbs.forEach(([k, h], i) => {
    const y = 3.5 + i * 0.71;
    box(s, 9.5, y, 3.2, 0.58);
    T(s, `${k}  ${h}`, { x: 9.68, y, w: 2.9, h: 0.58, fontSize: 14, valign: "middle" });
  });

  // ---------- 4. Universe ----------
  s = content("Data", "DATA · UNIVERSE", "Start from every SEC filer, not today's listings",
    "Firms that later failed stay in, which keeps survivorship bias out of the sample.");
  const funnel = [
    ["All SEC filers", [20547, 20547, 20547]],
    ["10-K filed before the peak", [10631, 11495, 13264]],
    ["Latest 10-K is recent", [5675, 5745, 5749]],
    ["Not a SPAC (SIC, trust assets, name)", [5574, 5440, 5500]],
    ["Not a fund or asset-backed issuer", [5512, 5382, 5432]],
    ["Public float above zero, or a common ticker", [5095, 5077, 5119]],
  ];
  T(s, "2020", { x: 6.0, y: 1.98, w: 0.75, h: 0.25, fontSize: 11, bold: true, color: CRASH[0].text, align: "right" });
  T(s, "2022", { x: 6.8, y: 1.98, w: 0.75, h: 0.25, fontSize: 11, bold: true, color: CRASH[1].text, align: "right" });
  T(s, "2025", { x: 7.6, y: 1.98, w: 0.75, h: 0.25, fontSize: 11, bold: true, color: CRASH[2].text, align: "right" });
  funnel.forEach(([lab, v], i) => {
    const y = 2.32 + i * 0.7;
    const mean = (v[0] + v[1] + v[2]) / 3;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y, w: 5.2 * (mean / 20547), h: 0.58, fill: { color: i === 5 ? K.blueFill : K.plane2 },
      line: { type: "none" }, objectName: oname("bar") });
    T(s, lab, { x: 0.72, y, w: 5.0, h: 0.58, fontSize: 13, valign: "middle", color: K.ink, bold: i === 5 });
    v.forEach((x, j) => T(s, x.toLocaleString("en-US"), { x: 6.0 + j * 0.8, y, w: 0.75, h: 0.58, fontSize: 13,
      align: "right", valign: "middle", bold: i === 5 }));
  });
  T(s, "15,291 firm-crash rows from 6,842 firms. Bar length: mean of the three crashes.",
    { x: 0.6, y: 6.55, w: 7.8, h: 0.3, fontSize: 12, color: K.muted });
  const uni = [
    ["A 10-K, not today's ticker list", "Foreign filers (Form 20-F) drop out; a dead firm's old 10-Ks keep it in."],
    ["SPACs, caught three ways", "SIC 6770, most assets held in trust, or a SPAC-style name at the peak. The trust tag alone removed Exelon and Aon."],
    ["Public stock, two ways", "Float above zero or a current common ticker. Float alone removed Fox and Tyson."],
  ];
  uni.forEach(([h, b], i) => {
    const y = 1.98 + i * 1.55;
    box(s, 8.8, y, 3.9, 1.38);
    T(s, h, { x: 9.0, y: y + 0.15, w: 3.55, h: 0.32, fontSize: 15, bold: true });
    T(s, b, { x: 9.0, y: y + 0.5, w: 3.55, h: 0.82, fontSize: 12.5, color: K.ink2 });
  });

  // ---------- 5. Tickers ----------
  s = content("Data", "DATA · TICKERS", "Giving each filer the right ticker",
    "SEC data names firms by CIK; prices need a ticker, and tickers get reused by other companies.");
  const tick = [["10,466", "SEC's current ticker"], ["2,917", "name match in the fails files (dead firms)"], ["9", "set by hand"]];
  tick.forEach(([v, l], i) => {
    const x = 0.6 + i * 2.75;
    box(s, x, 1.98, 2.55, 1.2);
    T(s, v, { x: x + 0.2, y: 2.08, w: 2.2, h: 0.5, fontSize: 26, bold: true, fontFace: HEAD });
    T(s, l, { x: x + 0.2, y: 2.62, w: 2.2, h: 0.5, fontSize: 12, color: K.ink2 });
  });
  T(s, "IDENTITY CHECK AT THE PEAK", { x: 0.6, y: 3.45, w: 8, h: 0.25, fontSize: 11, bold: true, color: K.muted, charSpacing: 1 });
  const flow = [
    ["Candidate ticker", "current or name-matched"],
    ["Fails file at the peak", "issuer code (first 6 of CUSIP) and name"],
    ["Same firm?", "same issuer, or a name the firm used within ±270 days"],
  ];
  flow.forEach(([h, b], i) => {
    const x = 0.6 + i * 2.75;
    box(s, x, 3.8, 2.4, 1.3, { fill: K.bg, line: K.rule });
    T(s, h, { x: x + 0.17, y: 3.92, w: 2.1, h: 0.32, fontSize: 14, bold: true });
    T(s, b, { x: x + 0.17, y: 4.27, w: 2.1, h: 0.75, fontSize: 12, color: K.muted });
    if (i < 2) arrow(s, x + 2.43, 4.45, x + 2.72, 4.45);
  });
  box(s, 0.6, 5.35, 3.8, 0.75, { fill: K.greenFill });
  T(s, [{ text: "Keep: ", options: { bold: true, color: K.green } }, { text: "the price check runs next" }],
    { x: 0.8, y: 5.35, w: 3.5, h: 0.75, fontSize: 13, valign: "middle" });
  box(s, 4.6, 5.35, 3.65, 0.75, { fill: K.redFill });
  T(s, [{ text: "Skip: ", options: { bold: true, color: K.red } }, { text: "another firm held the ticker (36 rows)" }],
    { x: 4.8, y: 5.35, w: 3.4, h: 0.75, fontSize: 13, valign: "middle" });
  T(s, "13,392 rows matched (87.6%). Hand check: 0 wrong in 100 random name matches.",
    { x: 0.6, y: 6.35, w: 7.8, h: 0.3, fontSize: 12, color: K.muted });
  box(s, 8.9, 1.98, 3.8, 4.12);
  T(s, "What the identity check caught", { x: 9.1, y: 2.12, w: 3.4, h: 0.32, fontSize: 15, bold: true });
  T(s, bullets([
    [{ text: "META", bold: true, color: K.ink }, { text: " in 2022 was Meta Materials, not Meta Platforms" }],
    [{ text: "Ambac", bold: true, color: K.ink }, { text: " was priced as Overseas Shipholding" }],
    [{ text: "iStar", bold: true, color: K.ink }, { text: " was priced as the old Safehold" }],
    [{ text: "BBBY", bold: true, color: K.ink }, { text: " in 2025 is a different company" }],
    [{ text: "11 labeled rows", bold: true, color: K.ink }, { text: " had been priced as another firm before this check" }],
  ], { size: 14, space: 10 }), { x: 9.1, y: 2.6, w: 3.45, h: 3.4 });

  // ---------- 6. Price check ----------
  s = content("Data", "DATA · PRICES", "Checking every price series against the SEC",
    "Fails-to-deliver files record a price for each ticker on many days: an independent check on the series.");
  img(s, "price_check_example.png", 0.6, 1.95, 8.0, "Yahoo CZR prices against SEC fails prices in 2020 (rejected) and 2022 (verified)");
  T(s, "The rule", { x: 9.0, y: 1.98, w: 3.7, h: 0.32, fontSize: 15, bold: true });
  T(s, bullets([
    "Within ±270 days of the peak, compare price levels on each fails date",
    "Allowed gap: 3% (5% under $5, 10% under $1); one split allowed",
    "At least 80% of dates must agree",
    "Yahoo first; Tiingo for firms that left the market",
  ], { size: 13, space: 8 }), { x: 9.0, y: 2.4, w: 3.7, h: 3.3 });
  const pc = [
    ["12,931", "of 13,392 matched rows have a checked price (96.6%)"],
    ["98%", "of days, Yahoo and Tiingo returns match exactly (428 shared tickers)"],
    ["Levels, not moves", "comparing daily moves passed the wrong company for calm stocks"],
  ];
  pc.forEach(([v, l], i) => {
    const x = 0.6 + i * 4.1;
    box(s, x, 5.92, 3.9, 0.98);
    T(s, v, { x: x + 0.2, y: 6.0, w: 3.5, h: 0.4, fontSize: 19, bold: true, fontFace: HEAD });
    T(s, l, { x: x + 0.2, y: 6.4, w: 3.55, h: 0.45, fontSize: 11.5, color: K.ink2 });
  });

  // ---------- 7. Cleaning and filters ----------
  s = content("Data", "DATA · CLEANING", "Cleaning prices, then filtering rows",
    "A bad print or a missed split creates a fake crash or a fake recovery, so prices are cleaned before any label.");
  const lc = [
    ["Rows with a checked price", 4031, 4282, 4618],
    ["Common stock only", 4026, 4276, 4605],
    ["20+ closes in the 30 days before the peak", 4008, 4272, 4568],
    ["Pre-crash price ≥ $1 (unadjusted)", 3491, 3816, 4010],
    ["Market value ≥ $10M", 3429, 3796, 3888],
    ["Traded on ≥ 70% of days in the prior year", 3216, 3599, 3744],
    ["Drop business development companies", 3216, 3599, 3698],
  ];
  const hdrCell = (t, color = K.ink2, align = "right") => ({ text: t, options: { bold: true, fontSize: 12, color, align, fill: { color: K.bg } } });
  const lrows = [[hdrCell("Step", K.ink2, "left"), hdrCell("2020", CRASH[0].text), hdrCell("2022", CRASH[1].text), hdrCell("2025", CRASH[2].text)]];
  lc.forEach((r, i) => {
    const last = i === lc.length - 1;
    lrows.push(r.map((v, j) => ({ text: j ? v.toLocaleString("en-US") : v, options: { fontSize: 13, bold: last,
      color: last ? K.ink : K.ink, align: j ? "right" : "left", fill: { color: last ? K.dark : i % 2 ? K.bg : K.plane } } })));
  });
  s.addTable(lrows, { x: 0.6, y: 1.98, w: 7.1, colW: [4.4, 0.9, 0.9, 0.9], rowH: 0.5, margin: [0, 0.12, 0, 0.12],
    valign: "middle", border: { type: "none" }, fontFace: BODY, objectName: "label-funnel" });
  T(s, "Final table: 10,513 rows. The $1 test uses the raw price (Yahoo × its split history), which agrees with SEC fails prices on 99.4% of rows.",
    { x: 0.6, y: 6.12, w: 7.1, h: 0.55, fontSize: 12, color: K.muted });
  const clean = [
    ["One-day spikes", "A move over 50% that's at least 75% undone the next day is removed.", "550 rows touched"],
    ["Missed reverse splits", "Fixed only when SEC share counts fall by the same ratio. On price alone, Novavax's real crash would have been “fixed.”", "18 rows fixed"],
    ["Stale prices", "More than 30% of days unchanged or untraded in the year before the peak.", "554 rows dropped"],
  ];
  clean.forEach(([h, b, tag], i) => {
    const y = 1.98 + i * 1.55;
    box(s, 8.1, y, 4.6, 1.38);
    T(s, h, { x: 8.3, y: y + 0.14, w: 2.6, h: 0.32, fontSize: 15, bold: true });
    T(s, tag, { x: 10.8, y: y + 0.15, w: 1.75, h: 0.3, fontSize: 11.5, bold: true, color: K.blue, align: "right" });
    T(s, b, { x: 8.3, y: y + 0.5, w: 4.25, h: 0.82, fontSize: 12.5, color: K.ink2 });
  });

  // ---------- 8. Labels ----------
  s = content("Data", "DATA · LABELS", "Turning prices into labels",
    "Every firm in a crash is measured from the same market dates: the S&P 500's peak and trough.");
  img(s, "label_example.png", 0.6, 1.92, 7.7, "Apple and Disney prices relative to their pre-crash price during the 2022 crash");
  const defs = [
    ["Recovered within 12 months", "main label", "Any close from the trough to 12 months later at or above the pre-crash price."],
    ["Beat the market", "second label", "Return from the peak to trough + 12 months above SPY's. A firm that stops trading keeps its last close."],
    ["Days to recovery", "survival", "Capped at 18 months. Only failed firms count as never recovering; acquisitions are censored."],
  ];
  defs.forEach(([h, tag, b], i) => {
    const y = 1.98 + i * 1.32;
    box(s, 8.65, y, 4.05, 1.18);
    T(s, h, { x: 8.83, y: y + 0.12, w: 2.75, h: 0.3, fontSize: 14, bold: true });
    T(s, tag, { x: 11.3, y: y + 0.13, w: 1.25, h: 0.28, fontSize: 11, color: K.muted, align: "right" });
    T(s, b, { x: 8.83, y: y + 0.44, w: 3.75, h: 0.7, fontSize: 12, color: K.ink2 });
  });
  const rates = [["Recovered", "75.6%", "42.8%", "69.2%"], ["Beat SPY", "47.7%", "32.0%", "38.4%"]];
  T(s, "Base rates", { x: 8.65, y: 5.98, w: 1.6, h: 0.3, fontSize: 12, bold: true, color: K.muted });
  CRASH.forEach((c, j) => T(s, c.key, { x: 10.35 + j * 0.8, y: 5.98, w: 0.75, h: 0.3, fontSize: 12, bold: true, color: c.text, align: "right" }));
  rates.forEach((r, i) => {
    T(s, r[0], { x: 8.65, y: 6.28 + i * 0.3, w: 1.9, h: 0.3, fontSize: 12, color: K.ink2 });
    r.slice(1).forEach((v, j) => T(s, v, { x: 10.35 + j * 0.8, y: 6.28 + i * 0.3, w: 0.75, h: 0.3, fontSize: 12, align: "right" }));
  });
  T(s, "Pre-crash price: the highest adjusted close in the 30 trading days up to the peak, so a dip on the peak day doesn't lower the bar.",
    { x: 0.6, y: 6.05, w: 7.7, h: 0.55, fontSize: 12, color: K.muted });

  // ---------- 9. Features ----------
  s = content("Data", "DATA · FEATURES", "Features: only what was known before the peak",
    "16 features per firm-crash, built so that nothing filed after the peak can leak in.");
  // timeline (2020 crash as the example)
  const tl = { x0: 0.8, x1: 12.5, y: 2.75 };
  s.addShape(pres.shapes.LINE, { x: tl.x0, y: tl.y, w: tl.x1 - tl.x0, h: 0, line: { color: K.ink2, width: 1.5 }, objectName: "timeline" });
  const peakX = 8.4;
  s.addShape(pres.shapes.RECTANGLE, { x: 2.4, y: tl.y - 0.16, w: peakX - 2.4, h: 0.32, fill: { color: K.blueFill }, line: { type: "none" }, objectName: "window" });
  T(s, "facts used: filed before the peak, for periods ending ≤ 550 days before it", { x: 2.4, y: tl.y - 0.5, w: peakX - 2.5, h: 0.28, fontSize: 11, color: K.blue, align: "center" });
  s.addShape(pres.shapes.LINE, { x: peakX, y: 1.95, w: 0, h: 1.65, line: { color: K.red, width: 2 }, objectName: "peak" });
  T(s, "peak · 2020-02-19", { x: peakX + 0.08, y: 1.95, w: 2.2, h: 0.28, fontSize: 12, bold: true, color: K.red });
  const marks = [
    [3.0, "10-K FY2018", "filed Mar 2019", true],
    [6.3, "10-Q Q3 2019", "filed Nov 2019", true],
    [9.4, "10-K FY2019", "filed Mar 2020", false],
    [11.6, "restated FY2018", "filed 2021", false],
  ];
  marks.forEach(([x, h, b, used]) => {
    dot(s, x - 0.1, tl.y - 0.1, 0.2, used ? K.blue : K.axis);
    T(s, h, { x: x - 1.0, y: tl.y + 0.25, w: 2.0, h: 0.28, fontSize: 12, bold: true, align: "center", color: used ? K.ink : K.muted });
    T(s, used ? b : `${b}: not used`, { x: x - 1.0, y: tl.y + 0.52, w: 2.0, h: 0.28, fontSize: 11, align: "center", color: K.muted });
  });
  const frules = [
    ["Point in time", "For each period, the latest value filed before the peak wins, so later restatements can't leak in. A test checks no fact or price is dated after the peak."],
    ["Trailing 12 months", "Flows = last full year + this year to date − the same period a year earlier. Hand-checked: Apple's revenue ($267.68B) matches."],
    ["Missing stays missing", "Missing values get a flag, not a zero. Current ratio and interest coverage are left out for financial firms."],
  ];
  frules.forEach(([h, b], i) => {
    const x = 0.6 + i * 4.1;
    T(s, h, { x, y: 3.78, w: 3.85, h: 0.3, fontSize: 14, bold: true });
    T(s, b, { x, y: 4.1, w: 3.85, h: 1.0, fontSize: 12, color: K.ink2 });
  });
  const groups = [
    ["Liquidity", "current ratio · cash / assets", false],
    ["Leverage", "debt / assets · liabilities / assets · interest coverage", false],
    ["Profitability", "net margin · operating margin · ROA · cash flow / assets", false],
    ["Growth and size", "revenue growth · asset growth · log assets", false],
    ["From prices", "log market value · 12-month volatility · momentum · beta", true],
  ];
  T(s, "12 FROM SEC FILINGS, 4 FROM PRICES, PLUS SECTOR (SIC DIVISION)", { x: 0.6, y: 5.25, w: 12, h: 0.25, fontSize: 11, bold: true, color: K.muted, charSpacing: 1 });
  groups.forEach(([h, b, price], i) => {
    const x = 0.6 + i * 2.46;
    box(s, x, 5.58, 2.3, 1.05, { fill: price ? K.blueFill : K.plane });
    T(s, h, { x: x + 0.15, y: 5.68, w: 2.0, h: 0.3, fontSize: 13, bold: true });
    T(s, b, { x: x + 0.15, y: 5.98, w: 2.05, h: 0.8, fontSize: 11.5, color: K.ink2 });
  });

  // ---------- 10. Evaluation design ----------
  pres.addSection({ title: "Models" });
  s = content("Models", "MODELS · EVALUATION", "How the models were tested",
    "Two settings: inside one crash, and across crashes. The second is the one a real user faces.");
  const gx = 1.75, gy = 2.5, cw = 1.75, ch = 0.92;
  T(s, "tested on →", { x: gx, y: 1.95, w: cw * 3, h: 0.25, fontSize: 12, color: K.muted, align: "center" });
  T(s, "trained on ↓", { x: 0.6, y: 2.18, w: 1.1, h: 0.25, fontSize: 12, color: K.muted });
  CRASH.forEach((c, j) => T(s, c.key, { x: gx + j * cw, y: 2.18, w: cw, h: 0.28, fontSize: 14, bold: true, align: "center", color: c.text }));
  const rowsG = ["2020", "2022", "2025", "other two"];
  rowsG.forEach((r, i) => {
    T(s, r, { x: 0.6, y: gy + i * ch, w: 1.1, h: ch, fontSize: 14, bold: true, valign: "middle", color: i < 3 ? CRASH[i].text : K.ink });
    CRASH.forEach((c, j) => {
      const within = i === j;
      const kind = within ? "within\n5-fold CV" : i === 3 ? "leave one\ncrash out" : j > i ? "forward" : "backward";
      const fill = within ? K.dark : i === 3 ? K.plane2 : j > i ? K.blueFill : K.plane;
      box(s, gx + j * cw + 0.05, gy + i * ch + 0.05, cw - 0.1, ch - 0.1, { fill });
      T(s, kind, { x: gx + j * cw, y: gy + i * ch, w: cw, h: ch, fontSize: 13, align: "center", valign: "middle",
        color: within || (j > i && i < 3) ? K.ink : K.ink });
    });
  });
  T(s, "Forward pairs are what real use looks like: train on the past, predict the next crash.",
    { x: 0.6, y: gy + 4 * ch + 0.15, w: 6.4, h: 0.5, fontSize: 12, color: K.muted });
  const evalWhy = [
    ["Keep each firm together", "71% of rows are firms that appear in all three crashes. Folds are grouped by firm, and bootstrap resamples draw whole firms, so a firm never sits on both sides."],
    ["AUC, not accuracy", "Base rates run from 43% to 76%: always guessing “recovers” is 76% accurate in 2020. AUC is the chance a recovering firm ranks above one that didn't; 0.5 is a coin flip."],
    ["Stratified folds", "Within a crash: 5 folds, stratified by the label and grouped by firm. Across crashes: train on one or two crashes, test on another, untouched."],
  ];
  evalWhy.forEach(([h, b], i) => {
    const y = 1.98 + i * 1.62;
    box(s, 7.5, y, 5.2, 1.52);
    num(s, i + 1, 7.7, y + 0.17);
    T(s, h, { x: 8.3, y: y + 0.18, w: 4.2, h: 0.35, fontSize: 15, bold: true });
    T(s, b, { x: 8.3, y: y + 0.53, w: 4.25, h: 0.95, fontSize: 12, color: K.ink2 });
  });

  // ---------- 11. Models ----------
  s = content("Models", "MODELS · PIPELINE", "Four models, one pipeline, no tuning",
    "Every model sees the same preprocessing, fit on the training rows only.");
  const pipe = [
    ["Cap ratios", "at the training 1st and 99th percentiles"],
    ["Fill missing", "training median, plus a missing flag"],
    ["Scale", "logistic models only"],
    ["Sector", "one-hot SIC division"],
    ["Classifier", "balanced class weights"],
  ];
  pipe.forEach(([h, b], i) => {
    const x = 0.6 + i * 2.48;
    box(s, x, 1.98, 2.2, 1.12, { fill: i === 4 ? K.dark : K.plane });
    T(s, h, { x: x + 0.15, y: 2.08, w: 1.9, h: 0.3, fontSize: 14, bold: true, color: i === 4 ? K.ink : K.ink });
    T(s, b, { x: x + 0.15, y: 2.4, w: 1.95, h: 0.62, fontSize: 11.5, color: i === 4 ? K.darkText : K.ink2 });
    if (i < 4) arrow(s, x + 2.23, 2.54, x + 2.45, 2.54);
  });
  const mh = (t) => ({ text: t, options: { fontSize: 12, color: K.muted, fill: { color: K.plane2 } } });
  const mrows = [[mh("Model"), mh("Inputs"), mh("Fixed settings")]];
  [
    ["Baseline (logistic)", "sector, log assets, log market value", "C = 0.5"],
    ["Logistic regression", "16 features + flags + sector", "C = 0.5"],
    ["Random forest", "same", "500 trees, min leaf 20"],
    ["LightGBM", "same", "300 trees, 15 leaves, rate 0.03, 80% row and column samples"],
  ].forEach((r, i) => mrows.push(r.map((t, j) => ({ text: t, options: { fontSize: 13, bold: j === 0, color: K.ink,
    fill: { color: i % 2 ? K.bg : K.plane } } }))));
  s.addTable(mrows, { x: 0.6, y: 3.45, w: 7.6, colW: [2.1, 2.7, 2.8], rowH: 0.55, margin: [0.04, 0.12, 0.04, 0.12],
    valign: "middle", border: { type: "none" }, fontFace: BODY, objectName: "models-table" });
  const mWhy = [
    ["Why a baseline?", "Sector and size alone already predict a lot. The question is what the fundamentals add on top."],
    ["Why no tuning?", "Tuning on one crash picks settings that fit that crash. Fixed, regularized defaults keep every comparison on equal terms."],
  ];
  mWhy.forEach(([h, b], i) => {
    const y = 3.45 + i * 1.62;
    box(s, 8.6, y, 4.1, 1.45);
    T(s, h, { x: 8.8, y: y + 0.15, w: 3.7, h: 0.32, fontSize: 15, bold: true });
    T(s, b, { x: 8.8, y: y + 0.5, w: 3.75, h: 0.9, fontSize: 12.5, color: K.ink2 });
  });
  T(s, "Fitting the caps and medians on training rows only means the test crash never shapes its own preprocessing.",
    { x: 0.6, y: 6.35, w: 7.6, h: 0.5, fontSize: 12, color: K.muted });

  // ---------- 12. Statistics ----------
  s = content("Models", "MODELS · MEASUREMENT", "What we measured, and how we tested it",
    "Every model is compared with the baseline on the same test rows, never on its own.");
  const stats = [
    ["DeLong test", "Model vs baseline AUC on the same rows. The two ROC curves are correlated, so the test accounts for it."],
    ["Holm correction", "Across all 72 comparisons (models × labels × train-test pairs), so a few lucky p-values can't carry the result."],
    ["Firm-grouped bootstrap", "95% intervals from resampling whole firms, since one firm's rows in different crashes aren't independent."],
    ["SHAP ranks", "Rank features by mean |SHAP| in each crash. Universal: top 5 in all three, same sign. Spearman compares the rankings."],
  ];
  stats.forEach(([h, b], i) => {
    const y = 1.98 + i * 1.2;
    num(s, i + 1, 0.6, y + 0.05);
    T(s, h, { x: 1.25, y, w: 5.8, h: 0.34, fontSize: 15, bold: true });
    T(s, b, { x: 1.25, y: y + 0.36, w: 5.9, h: 0.75, fontSize: 12.5, color: K.ink2 });
  });
  img(s, "shap_ranks.png", 7.35, 1.9, 5.35, "Feature importance rank per crash for the recovery label");
  T(s, "No feature is in the top 5 of all three crashes with the same sign.", { x: 7.35, y: 6.05, w: 5.35, h: 0.3, fontSize: 12, color: K.muted });

  // ---------- 13. Main result ----------
  pres.addSection({ title: "Results" });
  s = content("Results", "RESULTS · TRANSFER", "Real inside a crash, below the baseline across crashes",
    "Each square is LightGBM's AUC for recovering within 12 months: the chance it ranks a firm that recovered above one that didn't.");
  const tm = [[0.678, 0.457, 0.517], [0.456, 0.703, 0.602], [0.456, 0.579, 0.674], [0.422, 0.518, 0.546]];
  const tb = [[0.623, 0.468, 0.443], [0.463, 0.67, 0.618], [0.426, 0.633, 0.651]]; // baseline, same pairs
  const POS = ["1B3556", "1C5CAB", "3987E5", "86B6EF"], NEG = ["4A2223", "8E2E2E", "E34948", "F0A1A0"];
  const diverge = (v) => { // the page's diverge(v, 0.5, 0.25)
    const t = Math.max(-1, Math.min(1, (v - 0.5) / 0.25)), a = Math.abs(t);
    if (a < 0.12) return { bg: "33393F", fg: K.ink };
    const step = a < 0.35 ? 0 : a < 0.6 ? 1 : a < 0.85 ? 2 : 3;
    return { bg: (t > 0 ? POS : NEG)[step], fg: step >= 3 ? K.bg : "FFFFFF" };
  };
  const mx = 2.2, my = 2.35, mw = 1.86, mh2 = 0.98, gap = 0.07;
  T(s, "Tested on", { x: mx, y: 1.88, w: mw * 3, h: 0.22, fontSize: 11, color: K.muted, align: "center" });
  CRASH.forEach((c, j) => T(s, c.name.replace(/[()]/g, ""), { x: mx + j * mw, y: 2.08, w: mw, h: 0.25, fontSize: 12,
    color: K.ink2, align: "center" }));
  tm.forEach((r, i) => {
    const y = my + i * mh2;
    T(s, [{ text: i < 3 ? "Trained on" : "Trained on the", options: { color: K.muted, fontSize: 10.5, breakLine: true } },
      { text: i < 3 ? CRASH[i].name.replace(/[()]/g, "") : "other two", options: { color: K.ink2, fontSize: 12 } }],
      { x: 0.6, y, w: 1.55, h: mh2 - gap, valign: "middle" });
    r.forEach((v, j) => {
      const c = diverge(v), x = mx + j * mw, diag = i === j;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: mw - gap, h: mh2 - gap, rectRadius: 0.06, fill: { color: c.bg },
        line: diag ? { color: K.ink, width: 2 } : { type: "none" }, objectName: oname("cell") });
      T(s, v.toFixed(2), { x: x + 0.13, y: y + 0.06, w: mw - 0.3, h: 0.5, fontSize: 28, fontFace: HEAD, color: c.fg });
      const k = diag ? "same crash" : i < 3 ? `baseline ${tb[i][j].toFixed(2)}` : "";
      if (k) T(s, k, { x: x + 0.13, y: y + mh2 - 0.37, w: mw - 0.3, h: 0.24, fontSize: 10.5, color: c.fg });
    });
  });
  // the page's legend ramp
  [...NEG].reverse().concat(["33393F"], POS).forEach((col, k) => s.addShape(pres.shapes.RECTANGLE, {
    x: 2.6 + k * 0.2, y: 6.38, w: 0.2, h: 0.1, fill: { color: col }, line: { type: "none" }, objectName: oname("ramp") }));
  T(s, "0.25", { x: 2.1, y: 6.3, w: 0.45, h: 0.25, fontSize: 10.5, color: K.muted, align: "right" });
  T(s, "0.75", { x: 4.45, y: 6.3, w: 0.5, h: 0.25, fontSize: 10.5, color: K.muted });
  T(s, "Grey is a coin flip; red is worse than one.", { x: 5.0, y: 6.3, w: 3.2, h: 0.25, fontSize: 10.5, color: K.muted });
  const res = [
    ["+0.02 to +0.07", "AUC over the baseline within each crash; 16 of 18 gains significant after Holm", K.ink],
    ["−0.055", "AUC vs the baseline across crashes, pooled (95% CI −0.066 to −0.044)", K.red],
    ["0.602 vs 0.618", "2022 → 2025, the realistic forward test, vs the baseline: not significant", K.ink],
  ];
  res.forEach(([v, l, color], i) => {
    const y = 1.98 + i * 1.42;
    s.addShape(pres.shapes.LINE, { x: 8.6, y, w: 4.1, h: 0, line: { color: K.rule, width: 1 }, objectName: oname("rule") });
    T(s, v, { x: 8.6, y: y + 0.14, w: 4.1, h: 0.55, fontSize: 32, fontFace: HEAD, color });
    T(s, l, { x: 8.6, y: y + 0.72, w: 4.1, h: 0.5, fontSize: 12, color: K.ink2 });
  });

  // ---------- 14. Why ----------
  s = content("Results", "RESULTS · WHY", "Why: the same trait helped in one crash and hurt in the next",
    "Firms split into thirds by pre-crash volatility, within each crash.");
  img(s, "volatility_flip.png", 1.57, 1.88, 10.2, "Recovery and beat-SPY rates by pre-crash volatility third, per crash");
  const whyCards = [
    ["2020: liquidity panic", "Risky stocks fell hardest and bounced back hardest: the most volatile third beat SPY 59% of the time, vs 30%."],
    ["2022 and 2025: rate and trade shocks", "Money moved to safety: the most volatile third recovered least (27% vs 56% in 2022)."],
    ["Each crash has its own signals", "2020: cash and market value. 2022: asset growth and momentum. 2025: operating margin."],
  ];
  whyCards.forEach(([h, b], i) => {
    const x = 0.6 + i * 4.1;
    T(s, h, { x, y: 6.05, w: 3.9, h: 0.3, fontSize: 13.5, bold: true });
    T(s, b, { x, y: 6.35, w: 3.9, h: 0.5, fontSize: 11.5, color: K.ink2 });
  });

  // ---------- 15. Other methods ----------
  s = content("Results", "RESULTS · OTHER METHODS", "Archetypes, rules, exceptions, and timing",
    "Each method looks at the main result from another angle; each choice is listed with what it found.");
  const om = [
    ["Archetypes", "k-means", "Within-crash percentiles. k: best silhouette among solutions stable across seeds (ARI ≥ 0.8) → k = 3. HDBSCAN calls 77% noise, so these are broad tendencies.", "The archetype that recovers best changes with the crash."],
    ["Rules", "FP-Growth", "Features cut into within-crash thirds (low and high kept) plus sector; support 5%, lift ≥ 1.1: 91 / 640 / 326 rules.", "Few hold in all three; 2020's rules reverse in 2022 and 2025."],
    ["Exceptions", "Isolation Forest, LOF", "Isolation Forest flags the most unusual 2% of firm-crashes; LOF is the cross-check (they barely agree, Jaccard 0.08).", "211 flagged; they recovered less (49% vs 63%)."],
    ["Timing", "Kaplan–Meier, Cox", "Failure is the only non-recovery event. Cox is stratified by crash with firm-clustered errors.", "Median 247 / 539 / 142 days; only momentum is consistent."],
  ];
  om.forEach(([h, m, how, found], i) => {
    const y = 1.98 + i * 1.22;
    box(s, 0.6, y, 7.4, 1.1);
    T(s, h, { x: 0.8, y: y + 0.12, w: 1.6, h: 0.3, fontSize: 14, bold: true });
    T(s, m, { x: 0.8, y: y + 0.43, w: 1.6, h: 0.55, fontSize: 11, color: K.muted });
    T(s, how, { x: 2.5, y: y + 0.1, w: 5.35, h: 0.6, fontSize: 11.5, color: K.ink2 });
    T(s, found, { x: 2.5, y: y + 0.72, w: 5.35, h: 0.3, fontSize: 11.5, bold: true, color: K.ink });
  });
  img(s, "km_by_crash.png", 8.3, 1.98, 4.4, "Share of firms back at their pre-crash price by days after the trough, per crash");
  img(s, "archetype_recovery.png", 8.55, 4.3, 3.9, "Share recovered within 12 months by archetype and crash");

  // ---------- 16. Checks and limits ----------
  pres.addSection({ title: "Wrap-up" });
  s = content("Wrap-up", "WRAP-UP · ROBUSTNESS AND LIMITS", "Checking the result, and what it can't show",
    "The gap between within-crash and cross-crash AUC survives every check we tried.");
  const rh = (t, al = "center") => ({ text: t, options: { fontSize: 12, color: K.muted, align: al, fill: { color: K.plane2 } } });
  const rob = [
    ["Main result", "0.69", "0.51"],
    ["Drop 377 firms acquired early", "0.690", "0.510"],
    ["Beta-adjusted label", "0.702", "0.480"],
    ["Within-crash percentile features", "—", "−0.004"],
    ["Yahoo prices only", "±0.04", "≈ 0.5"],
    ["Peak-day close as pre-crash price", "same", "same"],
  ];
  const rrows = [[rh("Check", "left"), rh("Within"), rh("Across")]];
  rob.forEach((r, i) => rrows.push(r.map((t, j) => ({ text: t, options: { fontSize: 13, color: K.ink, align: j ? "center" : "left",
    fill: { color: i % 2 ? K.bg : K.plane } } }))));
  s.addTable(rrows, { x: 0.6, y: 1.98, w: 6.6, colW: [4.0, 1.3, 1.3], rowH: 0.52, margin: [0, 0.12, 0, 0.12],
    valign: "middle", border: { type: "none" }, fontFace: BODY, objectName: "robustness-table" });
  T(s, "LightGBM, mean AUC for recovery.", { x: 0.6, y: 5.75, w: 6.6, h: 0.3, fontSize: 12, color: K.muted });
  const lim = [
    ["Only three crashes", "Crash type can't be modeled directly; the link to cause is an interpretation."],
    ["Some survivorship left", "3.4% of matched rows have no checked price; they're smaller and fail more, mostly in 2020."],
    ["Checks with gaps", "7.5% of rows had no fails record to identity-check; SIC codes are today's, not the crash's."],
    ["Model assumptions", "Weak cluster structure; proportional hazards fail for some features."],
  ];
  lim.forEach(([h, b], i) => {
    const y = 1.98 + i * 1.15;
    box(s, 7.6, y, 5.1, 1.02);
    T(s, h, { x: 7.8, y: y + 0.12, w: 4.7, h: 0.3, fontSize: 14, bold: true });
    T(s, b, { x: 7.8, y: y + 0.43, w: 4.75, h: 0.55, fontSize: 12, color: K.ink2 });
  });

  // ---------- 17. Close ----------
  s = pres.addSlide({ masterName: "DARK", sectionTitle: "Wrap-up" });
  T(s, "What predicts recovery depends on what caused the crash", { x: 0.8, y: 0.85, w: 11.7, h: 1.5, fontFace: HEAD,
    fontSize: 42, color: K.ink, valign: "bottom" });
  const close = [
    ["Within a crash", "fundamentals beat sector and size (AUC ≈ 0.69)."],
    ["Across crashes", "the same models fall below that baseline (AUC ≈ 0.51)."],
    ["In practice", "don't trust a “crash-resilient” screen built on a past crash unless that crash had a similar cause."],
  ];
  close.forEach(([h, b], i) => {
    const y = 2.75 + i * 0.62;
    dot(s, 0.85, y + 0.1, 0.16, CRASH[i].color);
    T(s, [{ text: h + ": ", options: { bold: true, color: K.ink } }, { text: b, options: { color: K.darkText } }],
      { x: 1.2, y, w: 11.2, h: 0.5, fontSize: 18 });
  });
  T(s, "Questions?", { x: 0.8, y: 5.25, w: 6, h: 0.7, fontFace: HEAD, fontSize: 30, bold: true, color: K.ink });
  T(s, [
    { text: "Code, data, and report: github.com/raajbanga/crashRecovery", options: { breakLine: true } },
    { text: "Interactive results: raajbanga.github.io/crashRecovery" },
  ], { x: 0.8, y: 6.0, w: 8, h: 0.7, fontSize: 14, color: K.darkText });

  return pres;
}

(async () => {
  // pptxgenjs writes folder entries into the zip; some cloud viewers refuse those
  const tidy = (f) => { try { execFileSync("zip", ["-dq", f, "*/"]); } catch { /* none to remove */ } };
  await buildDeck().writeFile({ fileName: OUT });
  tidy(OUT);
  console.log("wrote", OUT);
  const pdf = OUT.replace(/\.pptx$/, ".pdf");
  try {
    execFileSync("osascript", ["-e", `tell application "Keynote"
      set d to open POSIX file "${OUT}"
      export d to POSIX file "${pdf}" as PDF
      close d saving no
    end tell`]);
    console.log("wrote", pdf);
  } catch (e) {
    console.warn("PDF export skipped (needs Keynote):", e.message.split("\n")[0]);
  }
})();
