const $ = (id) => document.getElementById(id);
const livePlayer = $('live-player');
const liveMessage = $('live-message');
const archivePlayer = $('archive-player');
const archiveMessage = $('archive-message');
const archiveOverlay = $('archive-overlay');
const state = { date: '', hour: new Date().getHours(), recordings: [], datalogs: [], alerts: [], health: [] };

function valueOrDash(value) { return value === null || value === undefined || value === '' ? '—' : value; }
function setMetric(id, value, alert) { const node = $(id); node.textContent = valueOrDash(value); node.classList.toggle('alert', Boolean(alert)); }
function localDate(date = new Date()) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`; }
function hourText(hour) { return `${String(hour).padStart(2, '0')}:00`; }

async function setupHlsFallback() {
  const source = '/live/front.m3u8';
  if (livePlayer.canPlayType('application/vnd.apple.mpegurl')) {
    livePlayer.src = source;
    liveMessage.hidden = true;
    return;
  }
  if (window.Hls && window.Hls.isSupported()) {
    const hls = new window.Hls({ lowLatencyMode: true });
    hls.loadSource(source);
    hls.attachMedia(livePlayer);
    hls.on(window.Hls.Events.MANIFEST_PARSED, () => { liveMessage.hidden = true; });
    return;
  }
  liveMessage.textContent = 'Live stream unavailable';
}

async function setupLive() {
  const peer = new RTCPeerConnection();
  peer.addTransceiver('video', { direction: 'recvonly' });
  peer.ontrack = (event) => { livePlayer.srcObject = event.streams[0]; liveMessage.hidden = true; };
  await peer.setLocalDescription(await peer.createOffer());
  await new Promise((resolve) => {
    if (peer.iceGatheringState === 'complete') resolve();
    else peer.addEventListener('icegatheringstatechange', () => { if (peer.iceGatheringState === 'complete') resolve(); });
  });
  const endpoint = `${location.protocol}//${location.hostname}:8889/front/whep`;
  const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/sdp' }, body: peer.localDescription.sdp });
  if (!response.ok) throw new Error(`WHEP ${response.status}`);
  await peer.setRemoteDescription({ type: 'answer', sdp: await response.text() });
}

function updateAggregate(sample) {
  if (!sample) return;
  setMetric('device-id', sample.device_id);
  setMetric('unit-no', sample.unit_no);
  const gps = sample.gps;
  setMetric('gps-position', gps && gps.valid ? `${Number(gps.latitude).toFixed(5)}, ${Number(gps.longitude).toFixed(5)}` : 'No fix', gps && !gps.valid);
  setMetric('gps-speed', gps && gps.speed_kph !== null ? `${Number(gps.speed_kph).toFixed(1)} km/h` : '—');
  const fatigue = sample.fatigue;
  setMetric('fatigue-eyes', fatigue && fatigue.closed_eyes ? 'Closed' : 'Normal', fatigue && fatigue.closed_eyes);
  setMetric('fatigue-yawn', fatigue && fatigue.yawning ? 'Detected' : 'Normal', fatigue && fatigue.yawning);
  const when = new Date(sample.timestamp_utc);
  $('telemetry-time').textContent = when.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  $('aggregate-age').textContent = `${Math.max(0, Math.round((Date.now() - when.getTime()) / 1000))}s ago`;
  $('service-status').textContent = 'Online';
}

async function refreshAggregate() {
  try {
    const response = await fetch('/api/aggregate', { cache: 'no-store' });
    if (response.ok && response.status !== 204) updateAggregate(await response.json());
  } catch (_error) { $('service-status').textContent = 'Offline'; }
}

function drawHealth() {
  const strip = $('health-strip');
  strip.replaceChildren();
  let green = 0;
  state.health.forEach((item) => {
    if (item.status === 'green') green += 1;
    const button = document.createElement('button');
    button.className = `health-hour ${item.status}`;
    button.type = 'button';
    button.title = `${hourText(item.hour)} · recording ${item.recording ? 'ok' : 'missing'} · datalog ${item.datalog ? 'ok' : 'missing'}`;
    button.textContent = String(item.hour).padStart(2, '0');
    button.addEventListener('click', () => loadArchiveHour(item.hour));
    strip.appendChild(button);
  });
  $('health-date').textContent = state.date;
  $('health-summary').textContent = `${green}/24 hours complete`;
}

async function refreshHealth() {
  const response = await fetch(`/api/health?date=${encodeURIComponent(state.date)}`, { cache: 'no-store' });
  const payload = await response.json();
  state.health = payload.hours || [];
  drawHealth();
}

function recordingTitle(item) {
  const started = item.started_at_utc ? new Date(item.started_at_utc) : new Date(item.modified_at_utc);
  return `${started.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · ${(item.duration_seconds || 0).toFixed(0)} sec`;
}

function nmeaCoordinate(value, latitude) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '--';
  const absolute = Math.abs(Number(value));
  const degrees = Math.floor(absolute);
  const minutes = ((absolute - degrees) * 60).toFixed(4).padStart(7, '0');
  const degreeText = String(degrees).padStart(latitude ? 2 : 3, '0');
  const positive = latitude ? 'N' : 'E';
  const negative = latitude ? 'S' : 'W';
  return `${degreeText}${minutes} ${Number(value) < 0 ? negative : positive}`;
}

function overlayText(data) {
  const gps = data.gps && data.gps.valid ? data.gps : null;
  const latitude = nmeaCoordinate(gps && gps.latitude, true);
  const longitude = nmeaCoordinate(gps && gps.longitude, false);
  const speed = gps && gps.speed_kph !== null && gps.speed_kph !== undefined ? String(Math.round(Number(gps.speed_kph))).padStart(3, '0') : '---';
  const payload = data.redis_payload || {};
  const acceleration = payload.acceleration ?? payload.acc ?? payload.ACC ?? payload.acc_status ?? '--';
  const timestamp = new Date(data.timestamp_utc);
  const date = `${String(timestamp.getDate()).padStart(2, '0')}-${String(timestamp.getMonth() + 1).padStart(2, '0')}-${timestamp.getFullYear()}`;
  const time = timestamp.toLocaleTimeString([], { hour12: false });
  const unit = data.unit_no || '--';
  return `${latitude}, ${longitude}, ${speed}KM/H  ACC:${String(acceleration).toUpperCase()}\nID: ${data.device_id || '--'}  Name: ${unit}\n${date} ${time}  ${unit}  CH1`;
}

function cueLines(cue) {
  let text = cue.text;
  try { text = overlayText(JSON.parse(cue.text)); } catch (_error) { }
  return String(text).split('\n');
}

function updateArchiveOverlay(cues) {
  const lines = ['', '', ''];
  Array.from(cues || []).forEach((cue) => {
    const cueText = cueLines(cue);
    if (cueText.length > 1) {
      cueText.slice(0, 3).forEach((text, index) => { lines[index] = text; });
      return;
    }
    const index = cueText[0].startsWith('ID:') ? 1 : /^\d{2}-\d{2}-\d{4} /.test(cueText[0]) ? 2 : 0;
    lines[index] = cueText[0];
  });
  archiveOverlay.querySelectorAll('.telemetry-line').forEach((line, index) => { line.textContent = lines[index]; });
  archiveOverlay.hidden = !lines.some((line) => line.trim());
}

function loadArchiveVideo(videoUrl, subtitleUrl, label, downloadUrl, downloadName, seekToUtc = null, startedAtUtc = null, downloadLabel = 'Download MP4 + VTT') {
  $('archive-viewer').hidden = false;
  $('archive-selection').textContent = label;
  $('download-recording').href = downloadUrl;
  $('download-recording').download = downloadName;
  $('download-recording').textContent = downloadLabel;
  $('download-recording').hidden = false;
  archivePlayer.pause();
  archivePlayer.removeAttribute('src');
  archivePlayer.querySelectorAll('track').forEach((track) => track.remove());
  archivePlayer.src = videoUrl;
  if (subtitleUrl) {
    const track = document.createElement('track');
    track.kind = 'metadata';
    track.src = subtitleUrl;
    track.default = true;
    archivePlayer.appendChild(track);
    archivePlayer.addEventListener('loadedmetadata', () => { if (archivePlayer.textTracks[0]) archivePlayer.textTracks[0].mode = 'hidden'; }, { once: true });
    archivePlayer.addEventListener('cuechange', () => updateArchiveOverlay(archivePlayer.textTracks[0] && archivePlayer.textTracks[0].activeCues));
  }
  if (seekToUtc) {
    archivePlayer.addEventListener('loadedmetadata', () => {
      const started = startedAtUtc ? new Date(startedAtUtc).getTime() : Date.now();
      const requested = new Date(seekToUtc).getTime();
      archivePlayer.currentTime = Math.max(0, Math.min((requested - started) / 1000, archivePlayer.duration || 0));
    }, { once: true });
  }
  archivePlayer.load();
  archiveMessage.hidden = true;
}

function selectClip(index, seekToUtc = null) {
  const item = state.recordings[index];
  if (!item) return;
  loadArchiveVideo(
    `/recordings/${encodeURIComponent(item.filename)}`,
    item.subtitle_filename ? `/recordings/${encodeURIComponent(item.subtitle_filename)}` : null,
    recordingTitle(item),
    `/recordings/${encodeURIComponent(item.filename)}/bundle`,
    `${item.filename.replace(/\.mp4$/i, '')}.zip`,
    seekToUtc,
    item.started_at_utc,
  );
  document.querySelectorAll('.recording-card').forEach((card, cardIndex) => card.classList.toggle('selected', cardIndex === index));
}

function drawRecordings() {
  const grid = $('recording-grid');
  grid.replaceChildren();
  $('archive-viewer').hidden = true;
  $('archive-overlay').hidden = true;
  $('download-recording').hidden = true;
  $('download-datalog').hidden = true;
  if (!state.recordings.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'Select an hour with recordings';
    grid.appendChild(empty);
    $('archive-viewer').hidden = true;
    return;
  }
  state.recordings.forEach((item, index) => {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'recording-card';
    const time = document.createElement('strong');
    time.textContent = recordingTitle(item).split(' · ')[0];
    const detail = document.createElement('span');
    detail.textContent = `${(item.duration_seconds || 0).toFixed(0)} sec · ${(item.size_bytes / 1048576).toFixed(1)} MB`;
    const stateLabel = document.createElement('small');
    stateLabel.textContent = item.complete ? 'Ready to play' : 'Finalizing';
    card.append(time, detail, stateLabel);
    card.addEventListener('click', () => selectClip(index));
    grid.appendChild(card);
  });
}

function datalogForHour(hour) {
  return state.datalogs.find((item) => {
    const date = new Date(item.hour_local);
    return localDate(date) === state.date && date.getHours() === hour;
  });
}

async function loadArchiveHour(hour) {
  state.hour = hour;
  document.querySelectorAll('.health-hour').forEach((button) => button.classList.toggle('selected', Number(button.textContent) === hour));
  const response = await fetch(`/api/recordings?date=${encodeURIComponent(state.date)}&hour=${hour}`, { cache: 'no-store' });
  state.recordings = await response.json();
  drawRecordings();
  const datalog = datalogForHour(hour);
  const download = $('download-datalog');
  if (datalog) { download.href = `/datalog/${encodeURIComponent(datalog.filename)}`; download.download = datalog.filename; download.hidden = false; } else download.hidden = true;
}

async function refreshDatalogs() {
  const response = await fetch('/api/datalogs', { cache: 'no-store' });
  state.datalogs = await response.json();
  const list = $('datalog-list');
  list.replaceChildren();
  $('datalog-count').textContent = `${state.datalogs.length} file${state.datalogs.length === 1 ? '' : 's'}`;
  if (!state.datalogs.length) { const empty = document.createElement('div'); empty.className = 'empty-state'; empty.textContent = 'No completed hourly datalog yet.'; list.appendChild(empty); return; }
  state.datalogs.forEach((item) => {
    const card = document.createElement('article');
    card.className = 'datalog-card';
    const title = document.createElement('strong');
    title.textContent = new Date(item.hour_local).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
    const detail = document.createElement('span');
    detail.textContent = `${item.rows.toLocaleString()} rows · ${(item.size_bytes / 1048576).toFixed(2)} MB`;
    const link = document.createElement('a');
    link.className = 'button secondary';
    link.href = `/datalog/${encodeURIComponent(item.filename)}`;
    link.download = item.filename;
    link.textContent = 'Download';
    card.append(title, detail, link);
    list.appendChild(card);
  });
}

function alertTitle(alert) {
  return alert.alert_type === 'closed_eyes' ? 'Closed eyes' : 'Yawning';
}

function alertStatus(alert) {
  return alert.state === 'complete' ? 'Complete' : alert.state === 'post' ? 'Post window' : 'Active';
}

function alertDuration(alert) {
  return alert.duration_seconds === null || alert.duration_seconds === undefined ? 'ongoing' : `${alert.duration_seconds.toFixed(1)}s detected`;
}

async function openAlert(alert) {
  state.date = localDate(new Date(alert.started_at_utc));
  $('archive-date').value = state.date;
  const response = await fetch(`/api/recordings?date=${encodeURIComponent(state.date)}`, { cache: 'no-store' });
  state.recordings = await response.json();
  const index = state.recordings.findIndex((item) => alert.recording_filenames.includes(item.filename));
  const selected = index >= 0 ? index : 0;
  state.hour = new Date(alert.started_at_utc).getHours();
  drawRecordings();
  const datalog = datalogForHour(state.hour);
  const download = $('download-datalog');
  if (datalog) { download.href = `/datalog/${encodeURIComponent(datalog.filename)}`; download.download = datalog.filename; download.hidden = false; } else download.hidden = true;
  if (alert.clip_filename) {
    loadArchiveVideo(
      `/alert-clips/${encodeURIComponent(alert.clip_filename)}`,
      alert.clip_subtitle_filename ? `/alert-clips/${encodeURIComponent(alert.clip_subtitle_filename)}` : null,
      `${alertTitle(alert)} · alert evidence`,
      `/alert-clips/${encodeURIComponent(alert.clip_filename)}/bundle`,
      `${alert.clip_filename.replace(/\.mp4$/i, '')}.zip`,
    );
  } else if (state.recordings.length) selectClip(selected, alert.evidence_start_utc);
  document.querySelector('.archive-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function drawAlerts() {
  const list = $('alert-list');
  list.replaceChildren();
  $('alert-count').textContent = `${state.alerts.length} event${state.alerts.length === 1 ? '' : 's'}`;
  if (!state.alerts.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'No fatigue alerts yet.';
    list.appendChild(empty);
    return;
  }
  state.alerts.forEach((alert) => {
    const card = document.createElement('article');
    card.className = 'alert-card';
    const content = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = alertTitle(alert);
    const detail = document.createElement('span');
    detail.textContent = `${new Date(alert.started_at_utc).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })} · ${alertDuration(alert)}`;
    const window = document.createElement('small');
    window.textContent = `Pre ${Math.max(0, (new Date(alert.triggered_at_utc) - new Date(alert.evidence_start_utc)) / 1000).toFixed(1)}s · On ${alertDuration(alert)} · ${alert.evidence_end_utc ? 'Post ready' : 'Post pending'}`;
    content.append(title, detail, window);
    const meta = document.createElement('div');
    meta.className = 'alert-meta';
    const status = document.createElement('span');
    status.className = `alert-state ${alert.state}`;
    status.textContent = alertStatus(alert);
    const links = document.createElement('span');
    links.textContent = `${alert.recording_filenames.length} recording · ${alert.datalog_filenames.length} datalog`;
    meta.append(status, links);
    if (alert.clip_filename) {
      const video = document.createElement('a');
      video.className = 'button secondary';
      video.href = `/alert-clips/${encodeURIComponent(alert.clip_filename)}`;
      video.textContent = 'Alert video';
      meta.appendChild(video);
      const bundle = document.createElement('a');
      bundle.className = 'button secondary';
      bundle.href = `/alert-clips/${encodeURIComponent(alert.clip_filename)}/bundle`;
      bundle.download = `${alert.clip_filename.replace(/\.mp4$/i, '')}.zip`;
      bundle.textContent = 'Download bundle';
      meta.appendChild(bundle);
    } else if (alert.recording_filenames.length) {
      alert.recording_filenames.forEach((filename, index) => {
        const video = document.createElement('a');
        video.className = 'button secondary';
        video.href = `/recordings/${encodeURIComponent(filename)}/bundle`;
        video.download = `${filename.replace(/\.mp4$/i, '')}.zip`;
        video.textContent = alert.recording_filenames.length === 1 ? 'Download video bundle' : `Video bundle ${index + 1}`;
        meta.appendChild(video);
      });
    } else {
      const unavailable = document.createElement('span');
      unavailable.className = 'alert-state complete';
      unavailable.textContent = 'Video unavailable';
      meta.appendChild(unavailable);
    }
    if (alert.datalog_filenames.length) {
      const datalog = document.createElement('a');
      datalog.className = 'button secondary';
      datalog.href = `/datalog/${encodeURIComponent(alert.datalog_filenames[0])}`;
      datalog.download = alert.datalog_filenames[0];
      datalog.textContent = 'Datalog';
      meta.appendChild(datalog);
    }
    if (alert.recording_filenames.length) {
      const button = document.createElement('button');
      button.className = 'button secondary';
      button.type = 'button';
      button.textContent = 'Open evidence';
      button.addEventListener('click', () => openAlert(alert));
      meta.appendChild(button);
    }
    card.append(content, meta);
    list.appendChild(card);
  });
}

async function refreshAlerts() {
  const response = await fetch(`/api/alerts?date=${encodeURIComponent(state.date)}`, { cache: 'no-store' });
  state.alerts = await response.json();
  drawAlerts();
}

async function refreshArchive() {
  await refreshDatalogs();
  await refreshHealth();
  await refreshAlerts();
  await loadArchiveHour(state.hour);
}

state.date = localDate();
$('archive-date').value = state.date;
$('archive-date').addEventListener('change', async (event) => { state.date = event.target.value; state.hour = 0; await refreshArchive(); });
setupLive().catch(() => setupHlsFallback());
refreshAggregate();
refreshArchive();
window.setInterval(refreshAggregate, 1000);
window.setInterval(refreshArchive, 15000);
