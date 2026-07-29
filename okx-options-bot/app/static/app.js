const REFRESH_MS = 15000;

function fmtUsd(v) {
  if (v === null || v === undefined) return "-";
  const sign = v > 0 ? "+" : "";
  return `${sign}$${v.toFixed(2)}`;
}

function fmtPct(v) {
  if (v === null || v === undefined) return "-";
  return `${v.toFixed(1)}%`;
}

function fmtNum(v, digits = 4) {
  if (v === null || v === undefined) return "-";
  return Number(v).toFixed(digits);
}

function fmtTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function pnlClass(v) {
  if (v === null || v === undefined) return "";
  return v > 0 ? "positive" : v < 0 ? "negative" : "";
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

function renderTiles(summary) {
  const tiles = [
    {
      label: "Total P&L",
      value: fmtUsd(summary.total_pnl),
      cls: pnlClass(summary.total_pnl),
    },
    { label: "Win rate", value: fmtPct(summary.win_rate), cls: "" },
    { label: "W / L / Push", value: `${summary.wins} / ${summary.losses} / ${summary.pushes}`, cls: "" },
    {
      label: "Streak",
      value: summary.current_streak_type
        ? `${summary.current_streak} ${summary.current_streak_type}`
        : "-",
      cls: summary.current_streak_type === "WIN" ? "win" : summary.current_streak_type === "LOSS" ? "loss" : "",
    },
    { label: "Max drawdown", value: `-$${summary.max_drawdown.toFixed(2)}`, cls: summary.max_drawdown > 0 ? "loss" : "" },
  ];

  document.getElementById("tiles").innerHTML = tiles
    .map(
      (t) => `<div class="tile"><div class="label">${t.label}</div><div class="value ${t.cls}">${t.value}</div></div>`
    )
    .join("");

  document.getElementById("stake").textContent = summary.stake_usd.toFixed(2);
  document.getElementById("threshold").textContent = summary.bias_threshold;
}

function renderBySymbol(bySymbol) {
  const symbols = Object.keys(bySymbol).sort();
  const el = document.getElementById("by-symbol");
  if (symbols.length === 0) {
    el.innerHTML = '<div class="empty">Пока нет закрытых ставок</div>';
    return;
  }
  el.innerHTML = symbols
    .map((sym) => {
      const s = bySymbol[sym];
      return `<div class="tile">
        <div class="label">${sym} · ставка $${s.stake_usd.toFixed(2)}</div>
        <div class="value ${pnlClass(s.pnl_usd)}">${fmtUsd(s.pnl_usd)}</div>
        <div class="label">${s.wins}W / ${s.losses}L / ${s.pushes}P · ${fmtPct(s.win_rate)}</div>
      </div>`;
    })
    .join("");
}

function renderOkxBalance(data) {
  const el = document.getElementById("okx-balance");
  if (!data.available) {
    el.innerHTML = `<div class="empty">Недоступно: ${data.reason || "неизвестная причина"}</div>`;
    return;
  }
  el.innerHTML = `
    <div class="tile">
      <div class="label">USDT баланс${data.demo ? " · demo" : ""}</div>
      <div class="value">$${data.avail_bal.toFixed(2)}</div>
      <div class="label">equity: $${data.eq.toFixed(2)}</div>
    </div>`;
}

function renderSettings(s) {
  const el = document.getElementById("settings");
  const rows = [
    ["Символы", s.symbols.join(", ")],
    ["Таймфрейм свечей", s.candle_bar],
    ["Интервал цикла", `${s.poll_interval_seconds}s`],
    ["Порог сигнала (bias)", `±${s.bias_threshold}`],
    ["Ставка по умолчанию", `$${s.stake_usd.toFixed(2)}`],
    [
      "Ставки по символам",
      Object.keys(s.stake_overrides).length
        ? Object.entries(s.stake_overrides)
            .map(([sym, amt]) => `${sym}: $${Number(amt).toFixed(2)}`)
            .join(", ")
        : "нет переопределений",
    ],
    ["Стартовый баланс (для статистики)", `$${s.starting_bankroll.toFixed(2)}`],
    ["Demo-режим OKX", s.okx_demo ? "да" : "нет"],
    ["OKX ключи настроены", s.okx_authenticated ? "да" : "нет"],
  ];
  el.innerHTML = rows
    .map(
      ([label, value]) =>
        `<div class="tile"><div class="label">${label}</div><div class="value">${value}</div></div>`
    )
    .join("");
}

function renderActivity(rows) {
  const tbody = document.querySelector("#activity-table tbody");
  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">Пока нет записей</td></tr>';
    return;
  }
  tbody.innerHTML = rows
    .map(
      (r) => `<tr>
        <td>${fmtTime(r.ts)}</td>
        <td>${r.symbol}</td>
        <td>${r.bias_label} (${r.bias_score > 0 ? "+" : ""}${r.bias_score})</td>
        <td>${r.message}</td>
      </tr>`
    )
    .join("");
}

function renderBets(bets) {
  const tbody = document.querySelector("#bets-table tbody");
  if (bets.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty">Пока нет ставок</td></tr>';
    return;
  }
  tbody.innerHTML = bets
    .map((b) => {
      const status = b.status === "OPEN" ? "OPEN" : b.result || "-";
      return `<tr>
        <td>${fmtTime(b.opened_at)}</td>
        <td>${b.symbol}</td>
        <td>${b.direction}</td>
        <td>${b.inst_id}</td>
        <td>${fmtNum(b.entry_price, 6)}</td>
        <td>${fmtNum(b.exit_price, 6)}</td>
        <td>$${b.stake_usd.toFixed(2)}</td>
        <td class="${pnlClass(b.pnl_usd)}">${fmtUsd(b.pnl_usd)}</td>
        <td><span class="badge ${status}">${status}</span></td>
      </tr>`;
    })
    .join("");
}

function renderEquityCurve(points) {
  const canvas = document.getElementById("equity-chart");
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 600;
  const height = canvas.clientHeight || 220;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  if (points.length < 2) {
    ctx.fillStyle = getComputedStyle(document.body).getPropertyValue("--muted");
    ctx.font = "13px sans-serif";
    ctx.fillText("Недостаточно данных для графика", 12, height / 2);
    return;
  }

  const values = points.map((p) => p.balance);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const padding = 24;

  const x = (i) => padding + (i / (points.length - 1)) * (width - padding * 2);
  const y = (v) => height - padding - ((v - min) / range) * (height - padding * 2);

  const last = values[values.length - 1];
  const first = values[0];
  const color = last >= first ? "#2ecc71" : "#ff5c5c";

  ctx.beginPath();
  ctx.moveTo(x(0), y(values[0]));
  values.forEach((v, i) => ctx.lineTo(x(i), y(v)));
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.lineTo(x(values.length - 1), height - padding);
  ctx.lineTo(x(0), height - padding);
  ctx.closePath();
  ctx.fillStyle = color + "22";
  ctx.fill();

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x(values.length - 1), y(last), 3.5, 0, Math.PI * 2);
  ctx.fill();
}

async function refresh() {
  try {
    const [summary, bets, curve, activity, okxBalance, settings] = await Promise.all([
      fetchJson("/api/summary"),
      fetchJson("/api/bets?limit=100"),
      fetchJson("/api/equity-curve"),
      fetchJson("/api/activity?limit=50"),
      fetchJson("/api/okx-balance"),
      fetchJson("/api/settings"),
    ]);
    renderTiles(summary);
    renderBySymbol(summary.by_symbol);
    renderBets(bets);
    renderEquityCurve(curve);
    renderActivity(activity);
    renderOkxBalance(okxBalance);
    renderSettings(settings);
  } catch (err) {
    console.error("refresh failed", err);
  }
}

refresh();
setInterval(refresh, REFRESH_MS);
window.addEventListener("resize", refresh);
