/* Shared certificate renderer — used by the operator console and the buyer page.
   buildCertificateHTML(cert) -> HTML string for the certificate card body.
   mountCertificate(container, cert) -> inject it and animate the gauge. */

const esc = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const fmt = (v, suf = "") => (v === null || v === undefined || v === "")
  ? '<span style="color:var(--muted)">not measured</span>' : esc(v) + suf;
const colorFor = soh => soh >= 80 ? 'var(--mint)' : (soh >= 70 ? 'var(--amber)' : 'var(--danger)');
const dlRow = (l, v) => '<div class="row"><span class="l">' + l + '</span><span class="v">' + v + '</span></div>';

function statusPill(status) {
  const s = (status || '').toLowerCase();
  let cls = 'good';
  if (s === 'high') cls = 'bad';
  else if (s === 'mild' || s === 'elevated') cls = 'warn';
  else if (s === 'not measured') cls = '';
  return '<span class="pill ' + cls + '">' + esc(status) + '</span>';
}

function buildCertificateHTML(c, opts = {}) {
  const s = c.summary, v = c.vehicle, bd = c.battery_detail, hs = c.how_scored, dq = c.data_quality, ver = c.verification;
  const soh = s.soh_percent, col = colorFor(soh);
  const cap = bd.capacity, ce = bd.cells, ir = bd.internal_resistance, cy = bd.cycles, us = bd.usage, en = bd.environment;

  const veh = [
    dlRow('Model', fmt(v.model)), dlRow('VIN / Reg', fmt(v.vin_or_regno)),
    dlRow('Chemistry', fmt(v.chemistry)), dlRow('Age', fmt(v.age_years, ' yrs')),
    dlRow('Odometer', fmt(Number(v.odometer_km).toLocaleString(), ' km')), dlRow('Usage', fmt(v.km_per_year, ' km/yr')),
    dlRow('Rated pack', fmt(v.rated_capacity_kwh, ' kWh')),
  ].join("");

  const detail = [
    '<div class="subhead">Capacity</div>',
    dlRow('Full charge now', fmt(cap.measured_full_kwh, ' kWh')), dlRow('Rated (new)', fmt(cap.rated_kwh, ' kWh')),
    dlRow('Capacity fade', fmt(cap.capacity_fade_percent, '%')), dlRow('Capacity-based SoH', fmt(cap.capacity_based_soh, '%')),
    '<div class="subhead">Cells</div>',
    dlRow('Cells sampled', fmt(ce.count_sampled)), dlRow('Voltage spread', fmt(ce.spread_mv, ' mV') + statusPill(ce.imbalance_status)),
    dlRow('Lowest cell', fmt(ce.min_mv, ' mV')), dlRow('Highest cell', fmt(ce.max_mv, ' mV')),
    '<div class="subhead">Internal resistance</div>',
    dlRow('Measured', fmt(ir.measured_mohm, ' mΩ')), dlRow('Healthy baseline', fmt(ir.baseline_mohm, ' mΩ')),
    dlRow('Ratio vs healthy', fmt(ir.ratio_vs_healthy, '×') + statusPill(ir.status)),
    '<div class="subhead">Cycles &amp; usage</div>',
    dlRow('Equivalent full cycles', fmt(Math.round(cy.equivalent_full_cycles))), dlRow('Cycle source', fmt(cy.source)),
    dlRow('Cycles / year', fmt(cy.per_year)), dlRow('Fast-charge share', us.dc_fastcharge_ratio != null ? Math.round(us.dc_fastcharge_ratio * 100) + '%' : fmt(null)),
    dlRow('Assumed efficiency', fmt(us.assumed_efficiency_km_per_kwh, ' km/kWh')), dlRow('Avg ambient temp', fmt(en.avg_ambient_temp_c, ' °C')),
  ].join("");

  const bk = [];
  if (hs.capacity_based_soh != null) bk.push('<div class="row"><span>Capacity-based SoH</span><span class="v">' + hs.capacity_based_soh + '%</span></div>');
  bk.push('<div class="row"><span>Ageing-model SoH</span><span class="v">' + hs.model_based_soh + '%</span></div>');
  bk.push('<div class="row"><span>&nbsp;&nbsp;↳ calendar (age) loss</span><span class="v neg">−' + hs.calendar_loss_percent + '%</span></div>');
  bk.push('<div class="row"><span>&nbsp;&nbsp;↳ cycle (usage) loss</span><span class="v neg">−' + hs.cycle_loss_percent + '%</span></div>');
  (hs.penalty_items || []).forEach(it => bk.push('<div class="row"><span>Penalty · ' + esc(it.label) + '</span><span class="v neg">−' + it.points + '%</span></div>'));
  bk.push('<div class="row total"><span>Final State of Health</span><span class="v">' + hs.final_soh_percent + '%</span></div>');

  const flagsHTML = (c.flags && c.flags.length)
    ? '<div class="sec"><h3>Warnings found</h3><div class="flags">' + c.flags.map(f =>
        '<div class="flag"><svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 3l9 16H3L12 3Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M12 10v4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="17" r="1" fill="currentColor"/></svg><span>' + esc(f) + '</span></div>'
      ).join("") + '</div></div>'
    : '';

  const chips = dq.measured.map(m => '<span class="chip yes">✓ ' + esc(m) + '</span>')
    .concat(dq.estimated_or_missing.map(m => '<span class="chip no">– ' + esc(m) + '</span>')).join("");

  const qr = 'https://api.qrserver.com/v1/create-qr-code/?size=130x130&margin=0&data=' + encodeURIComponent(ver.verify_url);
  const printBtn = opts.showPrint === false ? '' : '<button class="btn ghost no-print" onclick="window.print()">↓ Download PDF</button>';

  // status / validity banner
  const vu = c.validity ? new Date(c.validity.valid_until) : null;
  const revoked = c.status === 'revoked';
  const expired = !revoked && vu && new Date() > vu;
  let banner = '';
  if (revoked) banner = `<div class="cert-banner bad">⛔ This certificate has been revoked${c.revoke_reason ? ' — ' + esc(c.revoke_reason) : ''}. Do not rely on it.</div>`;
  else if (expired) banner = `<div class="cert-banner warn">⏳ Expired on ${esc(vu.toLocaleDateString())} — recommend a fresh Revv test.</div>`;
  const validRow = vu ? dlRow('Valid until', `${esc(vu.toLocaleDateString())}${revoked ? ' (revoked)' : (expired ? ' (expired)' : '')}`) : '';

  return `
    <div class="print-only print-letterhead">
      <div class="pl-left">
        <div class="pl-brand">⚡ Revv</div>
        <div class="pl-tag">Independent EV Battery Health Certificate</div>
      </div>
      <div class="pl-right">
        <div class="pl-id">${esc(c.certificate_id)}</div>
        <div class="pl-date">Issued ${esc(c.issued_at.replace('T',' ').replace('+00:00',' UTC'))}</div>
      </div>
    </div>
    <div class="cert-head">
      <div>
        <h2 style="font-size:17px">Battery Health Certificate</h2>
        <div class="cert-id">${esc(c.certificate_id)}  ·  issued ${esc(c.issued_at.replace('T',' '))}${c.issued_by ? '  ·  by ' + esc(c.issued_by) : ''}</div>
      </div>
      <div class="head-actions">
        <span class="verified"><svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M8.5 12.2l2.3 2.3 4.7-4.9" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Verified by Revv · Independent</span>
        ${printBtn}
      </div>
    </div>

    ${banner}
    <div class="cert-grid">
      <div class="gauge">
        <svg viewBox="0 0 200 120" role="img" aria-label="State of health gauge">
          <path d="M18 110 A82 82 0 0 1 182 110" fill="none" stroke="var(--line)" stroke-width="15" stroke-linecap="round"/>
          <path id="arc" d="M18 110 A82 82 0 0 1 182 110" fill="none" stroke="${col}" stroke-width="15" stroke-linecap="round"/>
        </svg>
        <div class="num"><div class="big" id="score">0<span style="font-size:.5em">%</span></div><div class="lbl">State of Health</div></div>
      </div>
      <div>
        <span class="verdict" style="color:${col};background:color-mix(in srgb,${col} 14%,transparent);border:1px solid color-mix(in srgb,${col} 36%,transparent)">${esc(s.verdict)}</span>
        <div class="recommend">${esc(s.recommendation)}</div>
        <div class="kv">
          <div class="row"><span>Range retained</span><span>~${Math.round(s.range_retained_percent)}%</span></div>
          <div class="row"><span>Est. life remaining</span><span>${s.remaining_life_years} yrs (to ${s.end_of_life_soh}%)</span></div>
          <div class="row"><span>Confidence</span><span>${esc(s.confidence)} (${s.confidence_score})</span></div>
        </div>
      </div>
    </div>

    <div class="sec"><h3>Vehicle</h3><div class="dl">${veh}</div></div>
    <div class="sec"><h3>Battery detail</h3><div class="dl">${detail}</div></div>
    <div class="sec"><h3>How Revv scored it</h3><div class="breakdown">${bk.join("")}</div></div>
    ${flagsHTML}
    <div class="sec"><h3>Data quality</h3>
      <div style="font-size:14px;margin-bottom:2px"><b>${dq.completeness_percent}%</b> of the battery could be measured directly.</div>
      <div class="dq-bar"><i style="width:${dq.completeness_percent}%"></i></div>
      <div class="chips">${chips}</div>
    </div>
    <div class="sec"><h3>Authenticity</h3>
      <div class="verify">
        <img src="${qr}" alt="Verification QR code">
        <div>
          <div class="vid">${esc(ver.verify_id)}</div>
          <div class="vtext">${esc(ver.note)} ${esc(ver.verify_url)}</div>
          ${vu ? `<div class="vtext" style="margin-top:6px"><b>Valid until ${esc(vu.toLocaleDateString())}</b> · ${c.validity.validity_days}-day validity</div>` : ''}
        </div>
      </div>
    </div>

    <details class="raw"><summary>Raw telemetry from the device (everything the dongle sent)</summary><pre>${esc(JSON.stringify(c.raw_telemetry, null, 2))}</pre></details>
    <div class="methodology">Method: ${esc(c.methodology)}. ${esc(c.validity_note)}</div>
    <div class="disclaimer">${esc(c.disclaimer)}</div>
    <div class="print-only print-footer">
      Verify this certificate at ${esc(ver.verify_url)} · Revv is an independent assessment, not affiliated with any carmaker.
    </div>
  `;
}

function animateGauge(root, soh) {
  const arc = root.querySelector('#arc'), scoreEl = root.querySelector('#score');
  if (!arc) return;
  const len = arc.getTotalLength();
  arc.style.strokeDasharray = len;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
    arc.style.strokeDashoffset = len * (1 - soh / 100); scoreEl.firstChild.nodeValue = Math.round(soh); return;
  }
  arc.style.strokeDashoffset = len;
  arc.style.transition = 'stroke-dashoffset 1.2s cubic-bezier(.22,1,.36,1)';
  requestAnimationFrame(() => arc.style.strokeDashoffset = len * (1 - soh / 100));
  let start = null;
  (function tick(ts) {
    if (!start) start = ts;
    const t = Math.min((ts - start) / 1200, 1);
    scoreEl.firstChild.nodeValue = Math.round((1 - Math.pow(1 - t, 3)) * soh);
    if (t < 1) requestAnimationFrame(tick);
  })(performance.now());
}

function mountCertificate(container, cert, opts = {}) {
  container.innerHTML = buildCertificateHTML(cert, opts);
  animateGauge(container, cert.summary.soh_percent);
}
