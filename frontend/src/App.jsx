import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";

function isoToday() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function fmtPct(x) {
  const n = Number(x);
  if (!Number.isFinite(n)) return "-";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(3)}%`;
}

function Money({ value }) {
  const n = Number(value);
  return <span>${Number.isFinite(n) ? n.toFixed(2) : "-"}</span>;
}

// Convert model outputs into a consistent "probability of predicted direction"
// Rule: if raw prob_up >= 0.5 => UP with prob = prob_up
// else => DOWN with prob = 1 - prob_up
function normalizePrediction(probUpRaw) {
  const p = Number(probUpRaw);
  if (!Number.isFinite(p)) return { dirUp: false, probDir: NaN };

  const dirUp = p >= 0.5;
  const probDir = dirUp ? p : 1 - p;
  return { dirUp, probDir };
}

function pct0to100(x) {
  const n = Number(x);
  if (!Number.isFinite(n)) return "-";
  return (n * 100).toFixed(0);
}

// Cleans the "why" string into friendlier terms
function friendlyWhy(s) {
  if (!s || typeof s !== "string") return "";
  return s
    .replaceAll("volume_ma_20", "20-day average volume")
    .replaceAll("ma_20", "20-day moving average")
    .replaceAll("vwap", "volume-weighted average price")
    .replaceAll("VWAP", "volume-weighted average price")
    .replaceAll("_", " ");
}

export default function App() {
  // frontend/.env or .env.production:
  // VITE_API_BASE=https://q2he5oj9r6.execute-api.us-east-2.amazonaws.com/prod
  const API = import.meta.env.VITE_API_BASE;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [items, setItems] = useState([]);

  const [predLoading, setPredLoading] = useState(false);
  const [predError, setPredError] = useState("");
  const [preds, setPreds] = useState([]);

  const [pickedDate, setPickedDate] = useState(isoToday());
  const userPickedRef = useRef(false);

  // Load movers
  useEffect(() => {
    let canceled = false;

    async function loadMovers() {
      setLoading(true);
      setError("");

      try {
        if (!API) throw new Error("Missing VITE_API_BASE");

        const res = await fetch(`${API}/movers`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();
        const list = Array.isArray(data)
          ? data
          : Array.isArray(data?.items)
          ? data.items
          : [];

        if (!canceled) setItems(list);
      } catch (e) {
        if (!canceled) setError(e?.message || String(e));
      } finally {
        if (!canceled) setLoading(false);
      }
    }

    loadMovers();
    return () => {
      canceled = true;
    };
  }, [API]);

  // Load predictions (response: { asof, predictions: [...] })
  useEffect(() => {
    let canceled = false;

    async function loadPredictions() {
      setPredLoading(true);
      setPredError("");

      try {
        if (!API) throw new Error("Missing VITE_API_BASE");

        const res = await fetch(`${API}/predict`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();
        const list = Array.isArray(data?.predictions) ? data.predictions : [];

        if (!canceled) setPreds(list);
      } catch (e) {
        if (!canceled) {
          setPreds([]);
          setPredError(e?.message || String(e));
        }
      } finally {
        if (!canceled) setPredLoading(false);
      }
    }

    loadPredictions();
    return () => {
      canceled = true;
    };
  }, [API]);

  const byDate = useMemo(() => {
    const m = new Map();
    for (const x of items) if (x?.date) m.set(x.date, x);
    return m;
  }, [items]);

  const latestDate = useMemo(() => {
    if (!items.length) return "";
    return items.reduce(
      (max, x) => (x.date > max ? x.date : max),
      items[0]?.date || ""
    );
  }, [items]);

  const earliestDate = useMemo(() => {
    if (!items.length) return "";
    return items.reduce(
      (min, x) => (x.date < min ? x.date : min),
      items[0]?.date || ""
    );
  }, [items]);

  useEffect(() => {
    if (!items.length) return;
    if (userPickedRef.current) return;

    const today = isoToday();
    const defaultDate = byDate.has(today) ? today : latestDate;
    if (defaultDate && defaultDate !== pickedDate) setPickedDate(defaultDate);
  }, [items, byDate, latestDate, pickedDate]);

  const selected = byDate.get(pickedDate);

  const onPick = (val) => {
    userPickedRef.current = true;
    setPickedDate(val);
  };

  return (
    <div className="page">
      <header className="header">
        <h1>Daily Top Stock Mover</h1>
        <p className="muted">Pick a day to see who moved the most.</p>
      </header>

      {/* Daily mover card */}
      <section className="card">
        <div className="row">
          <label className="label">
            Pick a date
            <input
              type="date"
              value={pickedDate}
              min={earliestDate || undefined}
              max={latestDate || undefined}
              onChange={(e) => onPick(e.target.value)}
            />
          </label>
        </div>

        {loading && <div className="muted">Loading…</div>}
        {error && <div className="error">Error: {error}</div>}

        {!loading && !error && (
          <div className="selected">
            {!selected ? (
              <div className="notice">
                <div>
                  No stored result for <b>{pickedDate}</b>.
                </div>
                {latestDate && (
                  <button className="btn" onClick={() => onPick(latestDate)}>
                    Jump to latest ({latestDate})
                  </button>
                )}
              </div>
            ) : (
              <div>
                <div className="kv">
                  <div className="k">Date</div>
                  <div className="v">{selected.date}</div>
                </div>

                <div className="kv">
                  <div className="k">Top mover</div>
                  <div className="v">{selected.ticker}</div>
                </div>

                <div className="kv">
                  <div className="k">Percent change</div>
                  <div className="v">
                    <span
                      className={
                        Number(selected.percent_change) >= 0
                          ? "pill gain"
                          : "pill loss"
                      }
                    >
                      {fmtPct(selected.percent_change)}
                    </span>
                  </div>
                </div>

                <div className="kv">
                  <div className="k">Close</div>
                  <div className="v">
                    <Money value={selected.close_price ?? selected.close} />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Prediction title as a blue header like the main header */}
      <header className="header" style={{ marginTop: 16 }}>
        <h1>Tomorrow’s Market Prediction</h1>
        <p className="muted">
        Random Forest binary classifier that predicts stock price direction (up/down) using volatility, momentum, and moving average indicators
        </p>
      </header>

      {/* Prediction content */}
      <section className="card">
        {predLoading && <div className="muted">Loading predictions…</div>}

        {!predLoading && predError && (
          <div className="muted small">Prediction service unavailable.</div>
        )}

        {!predLoading && !predError && !preds.length && (
          <div className="muted">Predictions will appear after market close.</div>
        )}

        {!predLoading && !predError && preds.length > 0 && (
          <div className="selected" style={{ gap: 12 }}>
            {preds.map((p) => {
              const { dirUp, probDir } = normalizePrediction(p.prob_up);
              const conf = pct0to100(probDir);
              const why = friendlyWhy(p.why);

              return (
                <div
                  key={p.ticker}
                  className="kv"
                  style={{ gridTemplateColumns: "160px 1fr" }}
                >
                  <div className="k">{p.ticker}</div>

                  <div style={{ display: "grid", gap: 8 }}>
                    <div className="row" style={{ alignItems: "center", gap: 10 }}>
                      <span className={dirUp ? "pill gain" : "pill loss"}>
                        {dirUp ? "UP" : "DOWN"}
                      </span>

                      <span className="muted small">
                        Confidence: <b>{conf}%</b>
                      </span>
                    </div>

                    {why ? (
                      <div className="muted small">{why}</div>
                    ) : (
                      <div className="muted small">No explanation available.</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="muted small" style={{ marginTop: 10 }}>
          Educational signal only. Not investment advice.
        </div>
      </section>
    </div>
  );
}
