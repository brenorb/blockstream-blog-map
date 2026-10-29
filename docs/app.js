/* Blockstream Blog Map: canvas renderer for posts (glowing dots) and generated ideas (gold stars). */
(async function () {
  const data = await (await fetch("data.json", { cache: "no-cache" })).json();
  const posts = data.posts;
  const ghosts = data.ghosts || [];
  const clusters = data.clusters;

  // ---------- colors ----------
  // Cluster hue follows the cluster's angle around the map center, so neighbors get related colors.
  const clusterColor = {};
  clusters.forEach((c) => {
    const ang = Math.atan2(c.y, c.x);
    const hue = ((ang / (2 * Math.PI)) * 360 + 360 + 200) % 360;
    clusterColor[c.id] = d3.hsl(hue, 0.85, 0.62).formatHex();
  });
  const years = posts.map((p) => +p.date.slice(0, 4));
  const yMin = d3.min(years), yMax = d3.max(years);
  const yearColor = (y) => d3.interpolateTurbo(0.12 + 0.8 * ((y - yMin) / (yMax - yMin || 1)));
  let colorMode = "cluster";
  const colorOf = (p) => (colorMode === "year" ? yearColor(+p.date.slice(0, 4)) : clusterColor[p.cluster]);
  const GOLD = "#ffb347";

  // ---------- canvas ----------
  const canvas = document.getElementById("map");
  const ctx = canvas.getContext("2d");
  let W = 0, H = 0, DPR = 1;
  let base = { k: 1, x: 0, y: 0 };
  let zt = d3.zoomIdentity;

  function resize() {
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * DPR; canvas.height = H * DPR;
    const xs = posts.map((p) => p.x), ys = posts.map((p) => p.y);
    const [x0, x1] = d3.extent(xs), [y0, y1] = d3.extent(ys);
    const mobile = W < 760;
    const padTop = mobile ? 110 : 130, padBottom = mobile ? 140 : 50;
    const availW = W - 60, availH = H - padTop - padBottom;
    const k = Math.min(availW / (x1 - x0), availH / (y1 - y0));
    base = { k, x: W / 2 - k * (x0 + x1) / 2, y: padTop + availH / 2 + k * (y0 + y1) / 2 };
    draw();
  }
  // world -> screen (y flipped so "up" is up)
  const sx = (x) => zt.applyX(base.x + base.k * x);
  const sy = (y) => zt.applyY(base.y - base.k * y);

  // glow sprites, cached per color
  const spriteCache = new Map();
  function sprite(color) {
    if (spriteCache.has(color)) return spriteCache.get(color);
    const s = 64, c = document.createElement("canvas");
    c.width = c.height = s;
    const g = c.getContext("2d");
    const rgb = d3.rgb(color);
    const grad = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
    grad.addColorStop(0, `rgba(${rgb.r},${rgb.g},${rgb.b},0.95)`);
    grad.addColorStop(0.18, `rgba(${rgb.r},${rgb.g},${rgb.b},0.55)`);
    grad.addColorStop(0.45, `rgba(${rgb.r},${rgb.g},${rgb.b},0.14)`);
    grad.addColorStop(1, `rgba(${rgb.r},${rgb.g},${rgb.b},0)`);
    g.fillStyle = grad;
    g.fillRect(0, 0, s, s);
    spriteCache.set(color, c);
    return c;
  }

  // faint background stars (deterministic)
  const rand = d3.randomLcg(7);
  const stars = d3.range(260).map(() => [rand(), rand(), rand()]);

  // ---------- state ----------
  let hidden = new Set();        // hidden cluster ids
  let query = "";
  let showGhosts = true;
  let hover = null;              // {type:'post'|'ghost', i}
  let selected = null;
  const matches = (p) => {
    if (hidden.has(p.cluster)) return false;
    if (!query) return true;
    const q = query.toLowerCase();
    return (p.title + " " + p.description + " " + p.tags.join(" ") + " " + p.authors.join(" ")).toLowerCase().includes(q);
  };

  // ---------- drawing ----------
  function starPath(x, y, r, inner) {
    ctx.beginPath();
    for (let i = 0; i < 8; i++) {
      const a = (i * Math.PI) / 4 - Math.PI / 2;
      const rr = i % 2 === 0 ? r : inner;
      ctx.lineTo(x + rr * Math.cos(a), y + rr * Math.sin(a));
    }
    ctx.closePath();
  }

  function draw(t = performance.now()) {
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "#05070c";
    ctx.fillRect(0, 0, W, H);

    // background stars
    for (const [a, b, c] of stars) {
      ctx.fillStyle = `rgba(160,180,210,${0.08 + c * 0.22})`;
      ctx.fillRect(a * W, b * H, c > 0.85 ? 1.6 : 1, c > 0.85 ? 1.6 : 1);
    }

    const zk = zt.k;
    const glow = Math.max(30, Math.min(80, 36 * Math.sqrt(zk)));
    const sel = selected;

    // neighbor lines for selection (drawn under points)
    if (sel) {
      const src = sel.type === "post" ? posts[sel.i] : ghosts[sel.i];
      const list = sel.type === "ghost" ? src.nn.slice(0, 5) : src.nn.slice(0, 6);
      ctx.save();
      ctx.setLineDash([4, 5]);
      for (const [j, s] of list) {
        const q = posts[j];
        ctx.strokeStyle = sel.type === "ghost" ? `rgba(255,179,71,${0.25 + s * 0.4})` : `rgba(99,214,240,${0.2 + s * 0.45})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(sx(src.x), sy(src.y));
        ctx.lineTo(sx(q.x), sy(q.y));
        ctx.stroke();
      }
      ctx.restore();
    }

    // posts: additive glow
    ctx.globalCompositeOperation = "lighter";
    for (const p of posts) {
      const on = matches(p);
      const col = colorOf(p);
      const x = sx(p.x), y = sy(p.y);
      if (x < -50 || y < -50 || x > W + 50 || y > H + 50) continue;
      ctx.globalAlpha = on ? 0.9 : 0.07;
      const g = glow * (p.words > 1500 ? 1.15 : 1);
      ctx.drawImage(sprite(col), x - g / 2, y - g / 2, g, g);
    }
    ctx.globalAlpha = 1;
    // cores
    for (const p of posts) {
      if (!matches(p)) continue;
      const x = sx(p.x), y = sy(p.y);
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      ctx.beginPath();
      ctx.arc(x, y, Math.max(1.1, Math.min(2.4, 1.2 * Math.sqrt(zk))), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";

    // cluster labels
    if (colorMode === "cluster") {
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      const fs = Math.max(12, Math.min(20, 13 * Math.sqrt(zk)));
      ctx.font = `600 ${fs}px "Barlow Condensed", sans-serif`;
      for (const c of clusters) {
        if (hidden.has(c.id)) continue;
        const x = sx(c.x), y = sy(c.y);
        ctx.globalAlpha = zk > 5 ? 0.35 : 0.9;
        ctx.fillStyle = "rgba(5,7,12,0.55)";
        const label = c.name.toUpperCase();
        const w = ctx.measureText(label).width;
        ctx.fillRect(x - w / 2 - 5, y - fs / 2 - 2, w + 10, fs + 4);
        ctx.fillStyle = clusterColor[c.id];
        ctx.fillText(label, x, y);
      }
      ctx.globalAlpha = 1;
    }

    // ghosts: gold four-point stars with a pulsing halo
    if (showGhosts) {
      ghosts.forEach((g, gi) => {
        const x = sx(g.x), y = sy(g.y);
        const pulse = 0.5 + 0.5 * Math.sin(t / 600 + gi);
        // hole the point was aimed at
        if (g.hole) {
          const hx = sx(g.hole.x), hy = sy(g.hole.y), hr = g.hole.r * base.k * zk;
          ctx.save();
          ctx.setLineDash([2, 6]);
          ctx.strokeStyle = `rgba(255,179,71,${0.18 + 0.12 * pulse})`;
          ctx.beginPath(); ctx.arc(hx, hy, hr, 0, Math.PI * 2); ctx.stroke();
          ctx.restore();
        }
        ctx.globalCompositeOperation = "lighter";
        const hs = 46 + 16 * pulse;
        ctx.globalAlpha = 0.85;
        ctx.drawImage(sprite(GOLD), x - hs / 2, y - hs / 2, hs, hs);
        ctx.globalAlpha = 1;
        ctx.globalCompositeOperation = "source-over";
        ctx.strokeStyle = `rgba(255,179,71,${0.5 + 0.4 * pulse})`;
        ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.arc(x, y, 11 + 3 * pulse, 0, Math.PI * 2); ctx.stroke();
        ctx.fillStyle = "#fff4dc";
        starPath(x, y, 10, 2.4);
        ctx.fill();
        ctx.fillStyle = GOLD;
        ctx.font = `700 12px "Barlow Condensed", sans-serif`;
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText(`NEW IDEA ${gi + 1}`, x + 16, y - 1);
      });
    }

    // hover / selection rings
    for (const s of [hover, selected]) {
      if (!s) continue;
      const p = s.type === "post" ? posts[s.i] : ghosts[s.i];
      ctx.strokeStyle = s.type === "ghost" ? GOLD : "#ffffff";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(sx(p.x), sy(p.y), s === selected ? 9 : 7, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  // animate only for the pulsing stars
  function loop(t) {
    draw(t);
    requestAnimationFrame(loop);
  }

  // ---------- interaction ----------
  const zoom = d3.zoom().scaleExtent([0.6, 14]).on("zoom", (e) => { zt = e.transform; });
  d3.select(canvas).call(zoom).on("dblclick.zoom", null);

  function pick(mx, my) {
    let best = null, bd = 14 * 14;
    if (showGhosts) ghosts.forEach((g, i) => {
      const d = (sx(g.x) - mx) ** 2 + (sy(g.y) - my) ** 2;
      if (d < 18 * 18 && d < bd + 200) { best = { type: "ghost", i }; bd = d; }
    });
    if (best) return best;
    posts.forEach((p, i) => {
      if (!matches(p)) return;
      const d = (sx(p.x) - mx) ** 2 + (sy(p.y) - my) ** 2;
      if (d < bd) { bd = d; best = { type: "post", i }; }
    });
    return best;
  }

  const tip = document.getElementById("tip");
  canvas.addEventListener("pointermove", (e) => {
    if (e.pointerType === "touch") return;
    hover = pick(e.clientX, e.clientY);
    canvas.classList.toggle("hovering", !!hover);
    if (!hover) { tip.hidden = true; return; }
    const p = hover.type === "post" ? posts[hover.i] : ghosts[hover.i];
    tip.innerHTML = hover.type === "ghost"
      ? `<div class="t" style="color:${GOLD}">★ ${esc(p.title)}</div><div class="m">Generated idea · not a real post</div>`
      : `<div class="t">${esc(p.title)}</div><div class="m">${p.date} · ${esc(clusters[p.cluster].name)}</div>`;
    tip.hidden = false;
    const tx = Math.min(e.clientX + 14, W - tip.offsetWidth - 8);
    const ty = Math.min(e.clientY + 14, H - tip.offsetHeight - 8);
    tip.style.left = tx + "px"; tip.style.top = ty + "px";
  });
  canvas.addEventListener("pointerleave", () => { hover = null; tip.hidden = true; });

  let downAt = null;
  canvas.addEventListener("pointerdown", (e) => { downAt = [e.clientX, e.clientY]; });
  canvas.addEventListener("click", (e) => {
    if (downAt && Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 5) return; // was a drag
    const hit = pick(e.clientX, e.clientY);
    select(hit);
  });

  // ---------- card ----------
  const card = document.getElementById("card");
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (v) => (v * 100).toFixed(v > 0.99 || v < 0.01 ? 1 : 0) + "%";

  function simBar(v) {
    const lo = 0.4, hi = 1.0, f = (x) => Math.max(0, Math.min(1, (x - lo) / (hi - lo))) * 100;
    const med = data.stats.median_twin;
    return `<div class="bar"><div class="track"></div><div class="fill" style="width:${f(v)}%"></div>
      <div class="tick" style="left:${f(med)}%"></div><div class="ticklabel" style="left:${f(med)}%">typical post</div>
      <div class="tick" style="left:${f(0.95)}%"></div><div class="ticklabel" style="left:${f(0.95)}%">near copy</div>
      <div class="knob" style="left:${f(v)}%"></div></div>`;
  }
  function nnList(list, n = 6) {
    return `<ul class="nn">${list.slice(0, n).map(([j, s]) => {
      const q = posts[j];
      return `<li data-i="${j}"><span class="s">${s.toFixed(2)}</span><span class="d" style="background:${clusterColor[q.cluster]}"></span><span class="t">${esc(q.title)}</span></li>`;
    }).join("")}</ul>`;
  }

  function select(s, opts = {}) {
    selected = s;
    if (!s) { card.hidden = true; history.replaceState(null, "", location.pathname); return; }
    const p = s.type === "post" ? posts[s.i] : ghosts[s.i];
    if (s.type === "post") {
      const c = clusters[p.cluster];
      card.className = "card";
      card.innerHTML = `<button class="close" aria-label="Close">×</button>
        <div class="label" style="color:${clusterColor[p.cluster]}">${esc(c.name)}</div>
        <h2><a href="${p.url}" target="_blank" rel="noopener">${esc(p.title)}</a></h2>
        <div class="meta">${p.date}${p.authors.length ? " · " + esc(p.authors.join(", ")) : ""} · ${p.words.toLocaleString()} words</div>
        ${p.description ? `<p>${esc(p.description)}</p>` : ""}
        ${p.tags.length ? `<div class="tags">${p.tags.map((t) => `<span>${esc(t)}</span>`).join("·")}</div>` : ""}
        <h3>Similarity to its closest post</h3>
        ${simBar(p.twin)}
        <div class="big"><b>${pct(p.closer)}</b><span>of posts have a closer twin</span></div>
        <h3>Nearest posts</h3>
        ${nnList(p.nn)}
        <a class="btn" href="${p.url}" target="_blank" rel="noopener">Read on blog →</a>`;
      history.replaceState(null, "", "#" + p.url.split("/").filter(Boolean).pop());
    } else {
      card.className = "card ghost";
      card.innerHTML = `<button class="close" aria-label="Close">×</button>
        <div class="label" style="color:${GOLD}">★ New idea ${s.i + 1} · ${esc(p.region || "")}</div>
        <div class="notice">Generated for an empty spot on the map. Not a real Blockstream post.</div>
        <h2>${esc(p.title)}</h2>
        <p>${esc(p.description)}</p>
        ${p.tags?.length ? `<div class="tags">${p.tags.map((t) => `<span>${esc(t)}</span>`).join("·")}</div>` : ""}
        ${p.why ? `<h3>Why it's new</h3><p>${esc(p.why)}</p>` : ""}
        ${p.lede ? `<h3>Draft opening</h3><p class="lede">${esc(p.lede)}</p>` : ""}
        <h3>Similarity to the closest real post</h3>
        ${simBar(p.twin)}
        <div class="big"><b>${pct(p.closer)}</b><span>of real posts have a closer twin</span></div>
        <div class="small">Closest real post: ${esc(posts[p.nn[0][0]].title)}</div>
        ${p.ingredients?.length ? `<h3>Blended from</h3>${nnList(p.ingredients.map((j) => [j, p.ingredient_sims?.[j] ?? 0]), 6)}` : ""}
        <h3>Nearest real posts</h3>
        ${nnList(p.nn, 5)}
        ${p.method ? `<h3>How it was found</h3><p class="small" style="line-height:1.5">${esc(p.method)}</p>` : ""}`;
      history.replaceState(null, "", "#idea-" + (s.i + 1));
    }
    card.hidden = false;
    card.scrollTop = 0;
    card.querySelector(".close").onclick = () => select(null);
    card.querySelectorAll(".nn li").forEach((li) => (li.onclick = () => select({ type: "post", i: +li.dataset.i }, { fly: true })));
    if (opts.fly) flyTo(p, null, opts.instant);
  }

  function flyTo(p, k, instant) {
    const kk = k || Math.max(zt.k, 2.2);
    const wx = base.x + base.k * p.x, wy = base.y - base.k * p.y;
    const cx = W < 760 ? W / 2 : W / 2 + 160, cy = W < 760 ? H * 0.3 : H / 2;
    const target = d3.zoomIdentity.translate(cx - kk * wx, cy - kk * wy).scale(kk);
    if (instant) d3.select(canvas).call(zoom.transform, target);
    else d3.select(canvas).transition().duration(750).call(zoom.transform, target);
  }

  // ---------- controls ----------
  const search = document.getElementById("search");
  search.addEventListener("input", () => { query = search.value.trim(); });
  search.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const hits = posts.filter(matches);
    if (hits.length) select({ type: "post", i: hits[0].i }, { fly: true });
  });
  document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".seg button").forEach((x) => x.classList.toggle("on", x === b));
    colorMode = b.dataset.color;
    renderLegend();
  }));
  const gBtn = document.getElementById("toggle-ghosts");
  gBtn.hidden = ghosts.length === 0;
  gBtn.addEventListener("click", () => {
    showGhosts = !showGhosts;
    gBtn.classList.toggle("on", showGhosts);
    if (!showGhosts && selected?.type === "ghost") select(null);
  });
  const legend = document.getElementById("legend");
  const lBtn = document.getElementById("toggle-legend");
  lBtn.addEventListener("click", () => { legend.hidden = !legend.hidden; lBtn.classList.toggle("on", !legend.hidden); });

  function renderLegend() {
    if (colorMode === "year") {
      const ys = d3.range(yMin, yMax + 1);
      legend.innerHTML = ys.map((y) => `<button disabled><span class="dot" style="color:${yearColor(y)};background:${yearColor(y)}"></span>${y}<span class="n">${years.filter((v) => v === y).length}</span></button>`).join("");
      return;
    }
    legend.innerHTML = clusters.slice().sort((a, b) => b.size - a.size).map((c) =>
      `<button data-c="${c.id}" class="${hidden.has(c.id) ? "off" : ""}" title="${esc(c.blurb)}"><span class="dot" style="color:${clusterColor[c.id]};background:${clusterColor[c.id]}"></span>${esc(c.name)}<span class="n">${c.size}</span></button>`
    ).join("") + (ghosts.length ? `<button disabled><span class="dot" style="color:${GOLD};background:${GOLD}"></span>★ Generated ideas<span class="n">${ghosts.length}</span></button>` : "");
    legend.querySelectorAll("button[data-c]").forEach((b) => b.addEventListener("click", () => {
      const id = +b.dataset.c;
      hidden.has(id) ? hidden.delete(id) : hidden.add(id);
      renderLegend();
    }));
  }

  // ---------- header text ----------
  const st = data.stats;
  document.getElementById("sub").innerHTML =
    `<b>${st.n}</b> posts, ${st.years[0]}–${st.years[1]}, placed by meaning. A typical post is <b>${Math.round(st.median_twin * 100)}%</b> similar to its closest twin.` +
    (ghosts.length ? ` <span style="color:${GOLD}">★ ${ghosts.length} gold stars</span> are generated ideas for the empty spots.` : "");
  document.getElementById("foot-model").textContent = data.model;

  renderLegend();
  window.addEventListener("resize", resize);
  resize();
  requestAnimationFrame(loop);

  // deep links: #slug or #idea-N
  function fromHash(e) {
    const instant = !e;
    const h = decodeURIComponent(location.hash.slice(1));
    if (h.startsWith("idea-") && ghosts[+h.slice(5) - 1]) select({ type: "ghost", i: +h.slice(5) - 1 }, { fly: true, instant });
    else if (h) {
      const p = posts.find((q) => q.url.split("/").filter(Boolean).pop() === h);
      if (p) select({ type: "post", i: p.i }, { fly: true, instant });
    }
  }
  window.addEventListener("hashchange", fromHash);
  fromHash();
  window.__map = { data, select, flyTo, zoom, canvas };
})();
