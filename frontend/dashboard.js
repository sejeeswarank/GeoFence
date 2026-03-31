import { initializeApp } from "https://www.gstatic.com/firebasejs/12.7.0/firebase-app.js";
import { getAuth, onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/12.7.0/firebase-auth.js";

const FRAME = { width: 640, height: 480 };
const API = window.location.origin;
const STORAGE_KEYS = {
  savedCameras: "saved_cameras",
  lastSelectedCamera: "geofence.lastSelectedCamera.v1",
};

let polling = false;
let hasFrame = false;
let drawPoints = [];
let uploadDrawPoints = [];
let uploadPreviewSize = { width: 0, height: 0 };
let currentUser = null;
let auth = null;
let booted = false;
let latestAlertId = 0;
let savedCameraConfigs = [];
let activeSavedCameraId = "";
let activeLocalCameraIndex = null;
let cameraConfigState = createEmptyCameraState();
let driveConfigured = false;
let cameraBuilderDraftMode = false;

const els = {
  accountIdentity: q("accountIdentity"),
  accountStatus: q("accountStatus"),
  alertsList: q("alertsList"),
  alertsMeta: q("alertsMeta"),
  btnAddCamera: q("btnAddCamera"),
  btnClearZone: q("btnClearZone"),
  btnCancelCameraSetup: q("btnCancelCameraSetup"),
  btnConnectDrive: q("btnConnectDrive"),
  btnFinishDrawing: q("btnFinishDrawing"),
  btnHomeClearAlerts: q("btnHomeClearAlerts"),
  btnLoadSnapshot: q("btnLoadSnapshot"),
  btnRefreshCameras: q("btnRefreshCameras"),
  btnSaveSnapshot: q("btnSaveSnapshot"),
  btnSetZone: q("btnSetZone"),
  btnSidebarSignOut: q("btnSidebarSignOut"),
  btnSignOut: q("btnSignOut"),
  btnStart: q("btnStart"),
  btnStop: q("btnStop"),
  btnSwitchCamera: q("btnSwitchCamera"),
  btnTestCamera: q("btnTestCamera"),
  cameraBuilder: q("cameraBuilder"),
  cameraBuilderNotice: q("cameraBuilderNotice"),
  cameraEmptyState: q("cameraEmptyState"),
  cameraPageMeta: q("cameraPageMeta"),
  cameraPlaceholder: q("cameraPlaceholder"),
  cameraSelect: q("cameraSelect"),
  cameraSourceType: q("cameraSourceType"),
  cameraVideoFeed: q("cameraVideoFeed"),
  cameraVideoStage: q("cameraVideoStage"),
  currentCameraName: q("currentCameraName"),
  detectionsList: q("detectionsList"),
  drawHint: q("drawHint"),
  driveConnectGroup: q("driveConnectGroup"),
  driveState: q("driveState"),
  driveSyncGroup: q("driveSyncGroup"),
  errorNote: q("errorNote"),
  fpsMeta: q("fpsMeta"),
  homeCameraMeta: q("homeCameraMeta"),
  homeActiveCameraInfo: q("homeActiveCameraInfo"),
  homeActiveCameraName: q("homeActiveCameraName"),
  homeCameraSelect: q("homeCameraSelect"),
  homePlaceholder: q("homePlaceholder"),
  homeVideoFeed: q("homeVideoFeed"),
  ipCameraUrl: q("ipCameraUrl"),
  ipSourceGroup: q("ipSourceGroup"),
  localSourceGroup: q("localSourceGroup"),
  localControls: q("localControls"),
  ipControls: q("ipControls"),
  navAccount: q("navAccount"),
  navAvatar: q("navAvatar"),
  navSavedCameras: q("navSavedCameras"),
  navUploadVideo: q("navUploadVideo"),
  navDisplayName: q("navDisplayName"),
  navHome: q("navHome"),
  pageAccount: q("pageAccount"),
  pageSavedCameras: q("pageSavedCameras"),
  pageHome: q("pageHome"),
  pageUploadVideo: q("pageUploadVideo"),
  preprocessState: q("preprocessState"),
  savedCameraList: q("savedCameraList"),
  statusPill: q("statusPill"),
  statusText: q("statusText"),
  trackingState: q("trackingState"),
  uploadAlerts: q("uploadAlerts"),
  btnAnalyzeVideo: q("btnAnalyzeVideo"),
  btnUploadClearAlerts: q("btnUploadClearAlerts"),
  btnUploadClearZone: q("btnUploadClearZone"),
  btnUploadFinishDrawing: q("btnUploadFinishDrawing"),
  uploadPreviewImage: q("uploadPreviewImage"),
  uploadPreviewPlaceholder: q("uploadPreviewPlaceholder"),
  uploadPreviewStage: q("uploadPreviewStage"),
  uploadSummary: q("uploadSummary"),
  uploadVideoFile: q("uploadVideoFile"),
  uploadVideoState: q("uploadVideoState"),
  uploadZoneCanvas: q("uploadZoneCanvas"),
  uploadZoneHint: q("uploadZoneHint"),
  uploadZoneMode: q("uploadZoneMode"),
  uploadZoneName: q("uploadZoneName"),
  uploadZonePoints: q("uploadZonePoints"),
  videoZoneCanvas: q("zoneCanvas"),
  zoneMode: q("zoneMode"),
  zoneName: q("zoneName"),
  zonePoints: q("zonePoints"),
  zoneState: q("zoneState"),
};

function q(id) {
  return document.getElementById(id);
}

function api(path, options) {
  return fetch(`${API}${path}`, options);
}

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setNotice(text, type = "") {
  els.accountStatus.textContent = text;
  els.accountStatus.className = `notice ${type}`.trim();
}

function showError(text) {
  els.errorNote.style.display = text ? "block" : "none";
  els.errorNote.textContent = text || "";
}

function setZoneState(text, isOk = false) {
  els.zoneState.textContent = text;
  els.zoneState.className = isOk ? "state ok" : "state";
}

function setUploadState(text, isOk = false) {
  els.uploadVideoState.textContent = text;
  els.uploadVideoState.className = isOk ? "state ok" : "state";
}

function createEmptyCameraState() {
  return {
    camera_name: "",
    camera_url: "",
    zone_name: "",
    polygon_points: [],
  };
}

function showCameraBuilder(options = {}) {
  if (els.cameraEmptyState) {
    els.cameraEmptyState.hidden = true;
  }
  if (els.cameraBuilder) {
    els.cameraBuilder.hidden = false;
  }
  if (els.cameraBuilderNotice && !options.keepNotice) {
    els.cameraBuilderNotice.hidden = true;
  }
  redrawCanvas();
  updateActionButtons();
}

function hideCameraBuilder(message = "") {
  cameraBuilderDraftMode = false;
  if (els.cameraBuilder) {
    els.cameraBuilder.hidden = true;
  }
  if (els.cameraEmptyState) {
    els.cameraEmptyState.hidden = false;
  }
  if (els.cameraBuilderNotice) {
    els.cameraBuilderNotice.textContent = message || "Camera saved successfully.";
    els.cameraBuilderNotice.hidden = !message;
  }
  updateActionButtons();
}

function startAddCameraFlow() {
  cameraBuilderDraftMode = true;
  setPage("saved");
  activeSavedCameraId = "";
  els.cameraSourceType.value = "ip";
  els.ipCameraUrl.value = "";
  els.currentCameraName.value = "";
  delete els.currentCameraName.dataset.userEdited;
  els.zoneName.value = "";
  drawPoints = [];
  els.zonePoints.value = "";
  els.zoneMode.value = "draw";
  cameraConfigState = createEmptyCameraState();
  els.cameraVideoFeed.removeAttribute("src");
  setFeedVisible(els.cameraVideoFeed, els.cameraPlaceholder, false);
  setPlaceholderContent(
    els.cameraPlaceholder,
    "Camera preview is idle",
    "Choose a new source, test it, then start the pipeline.",
  );
  renderDetections([]);
  applySourceMode();
  setZoneState("Draw a new zone for this camera, then save it.", false);
  showError("");
  showCameraBuilder();
}

function updateCameraEmptyState() {
  if (els.homeActiveCameraInfo && !savedCameraConfigs.length && !activeSavedCameraId) {
    els.homeActiveCameraInfo.textContent = "No cameras added. Go to Saved Cameras to add one.";
  }
}

function getScopedStorageKey(key) {
  const uid = currentUser?.uid || "anonymous";
  return `${key}:${uid}`;
}

function readStoredJson(key, fallback) {
  try {
    const raw = window.localStorage.getItem(getScopedStorageKey(key));
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function readStoredText(key, fallback = "") {
  try {
    return window.localStorage.getItem(getScopedStorageKey(key)) || fallback;
  } catch {
    return fallback;
  }
}

function writeStoredJson(key, value) {
  try {
    window.localStorage.setItem(getScopedStorageKey(key), JSON.stringify(value));
  } catch {
    // Ignore storage failures and continue with in-memory state.
  }
}

function setStoredText(key, value) {
  try {
    const storageKey = getScopedStorageKey(key);
    if (value) {
      window.localStorage.setItem(storageKey, value);
    } else {
      window.localStorage.removeItem(storageKey);
    }
  } catch {
    // Ignore storage failures and continue with in-memory state.
  }
}

function createSavedCameraId() {
  return `camera-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function readJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || "Request failed.");
  }
  return payload;
}

async function authApi(path, options = {}) {
  if (!currentUser) {
    throw new Error("No authenticated user.");
  }

  const token = await currentUser.getIdToken();
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  return api(path, { ...options, headers });
}

async function sessionApi(path, options = {}) {
  if (currentUser) {
    return authApi(path, options);
  }
  return api(path, options);
}

function currentSourceType() {
  return els.cameraSourceType.value;
}

function isLocalSource() {
  return currentSourceType() === "local";
}

function isDrawMode() {
  return els.zoneMode.value === "draw";
}

function isUploadDrawMode() {
  return els.uploadZoneMode.value === "draw";
}

function addDefaultScheme(value, scheme) {
  if (!value || /^[a-zA-Z][a-zA-Z\d+\-.]*:/.test(value)) {
    return value;
  }
  return `${scheme}${value}`;
}

function normalizeSourceUrl(type, value) {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }

  const candidate = type === "mobile" && !trimmed.includes("://") ? `http://${trimmed}` : trimmed;

  try {
    const url = new URL(candidate);
    if (type === "mobile" && (!url.pathname || url.pathname === "/")) {
      url.pathname = "/video";
    }
    return url.toString();
  } catch {
    return candidate;
  }
}

function getSourceInputValue(type) {
  if (type === "ip" || type === "mobile") {
    return els.ipCameraUrl.value.trim();
  }
  return "";
}

function prepareSourceUrl(type) {
  if (type !== "ip" && type !== "mobile") {
    return "";
  }

  const field = els.ipCameraUrl;
  const normalized = normalizeSourceUrl(type, field.value);
  if (normalized && field.value !== normalized) {
    field.value = normalized;
  }
  return normalized;
}

function normalizePoints(points) {
  if (!Array.isArray(points)) {
    return null;
  }

  const normalized = [];
  for (const point of points) {
    if (!Array.isArray(point) || point.length < 2) {
      return null;
    }

    const x = Number(point[0]);
    const y = Number(point[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return null;
    }
    normalized.push([Math.round(x), Math.round(y)]);
  }

  return normalized;
}

function parseZonePointsInput() {
  try {
    return normalizePoints(JSON.parse(els.zonePoints.value || "[]"));
  } catch {
    return null;
  }
}

function getDraftPoints() {
  return isDrawMode() ? drawPoints : parseZonePointsInput();
}

function parseUploadZonePointsInput() {
  try {
    return normalizePoints(JSON.parse(els.uploadZonePoints.value || "[]"));
  } catch {
    return null;
  }
}

function getUploadDraftPoints() {
  return isUploadDrawMode() ? uploadDrawPoints : parseUploadZonePointsInput();
}

function getSelectedLocalCameraLabel() {
  return (els.cameraSelect.selectedOptions[0]?.textContent || "Local Camera").replace(" (selected)", "");
}

function getDraftCameraName() {
  return els.currentCameraName.value.trim() || cameraConfigState.camera_name || "";
}

function getSourceIdentity() {
  const draftName = getDraftCameraName();
  if (draftName) {
    return draftName;
  }

  if (currentSourceType() === "local") {
    return getSelectedLocalCameraLabel();
  }

  return activeSavedCameraId ? findSavedCameraById(activeSavedCameraId)?.camera_name || "New Camera" : "New Camera";
}

function getDefaultZoneName() {
  const cameraName = getDraftCameraName();
  return cameraName ? `${cameraName} Zone` : "Zone A";
}

function normalizeSavedCamera(camera) {
  if (!camera || typeof camera !== "object") {
    return null;
  }

  const polygonPoints =
    normalizePoints(camera.polygon_points || camera.polygonPoints || camera.points || []) || [];
  const cameraName = String(camera.camera_name || camera.name || "").trim();
  const cameraUrl = String(camera.camera_url || camera.url || "").trim();
  const zoneName = String(camera.zone_name || camera.zoneName || "").trim();
  const sourceType = String(camera.source_type || "").trim();

  return {
    id: String(camera.id || createSavedCameraId()),
    camera_name: cameraName || "Saved Camera",
    camera_url: cameraUrl,
    zone_name: zoneName || "Zone A",
    polygon_points: polygonPoints,
    source_type: sourceType,
  };
}

function applySavedCameraConfigs(cameras, options = {}) {
  savedCameraConfigs = Array.isArray(cameras)
    ? cameras.map(normalizeSavedCamera).filter(Boolean)
    : [];
  savedCameraConfigs.sort((left, right) => left.camera_name.localeCompare(right.camera_name));

  const requestedActiveId = options.activeId ?? readStoredText(STORAGE_KEYS.lastSelectedCamera, "");
  activeSavedCameraId = findSavedCameraById(requestedActiveId) ? requestedActiveId : "";

  writeStoredJson(STORAGE_KEYS.savedCameras, savedCameraConfigs);
  setStoredText(STORAGE_KEYS.lastSelectedCamera, activeSavedCameraId);
  renderSavedCameraDropdown();
  renderSavedCameraList();
  updateCameraEmptyState();
}

function loadSavedCameraConfigs() {
  const stored = readStoredJson(STORAGE_KEYS.savedCameras, []);
  applySavedCameraConfigs(stored, { activeId: readStoredText(STORAGE_KEYS.lastSelectedCamera, "") });
}

async function syncSavedCameraConfigsToDrive(options = {}) {
  if (!driveConfigured || !currentUser) {
    return null;
  }

  const payload = await readJson(
    await authApi("/storage/cameras", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        saved_cameras: savedCameraConfigs,
        last_selected_camera_id: activeSavedCameraId,
        profile: getCurrentUserProfile(),
      }),
    }),
  );

  if (Array.isArray(payload.saved_cameras)) {
    applySavedCameraConfigs(payload.saved_cameras, { activeId: payload.last_selected_camera_id || activeSavedCameraId });
  }

  if (!options.quiet) {
    setNotice("Saved camera data synced to your Drive.", "ok");
  }

  return payload;
}

async function hydrateSavedCameraConfigs(storage) {
  loadSavedCameraConfigs();

  if (!driveConfigured || !currentUser) {
    return;
  }

  const payload = storage && typeof storage === "object"
    ? storage
    : await readJson(await authApi("/storage/cameras"));

  if (payload.status === "loaded") {
    applySavedCameraConfigs(payload.saved_cameras || [], {
      activeId: payload.last_selected_camera_id || readStoredText(STORAGE_KEYS.lastSelectedCamera, ""),
    });
    return;
  }

  await syncSavedCameraConfigsToDrive({ quiet: true });
}

async function persistSavedCameraConfigs(options = {}) {
  savedCameraConfigs.sort((left, right) => left.camera_name.localeCompare(right.camera_name));
  writeStoredJson(STORAGE_KEYS.savedCameras, savedCameraConfigs);
  renderSavedCameraDropdown();
  renderSavedCameraList();
  updateCameraEmptyState();

  if (!options.skipRemoteSync) {
    await syncSavedCameraConfigsToDrive({ quiet: options.quiet !== false });
  }
}

function setActiveSavedCamera(id = "", options = {}) {
  activeSavedCameraId = id || "";
  setStoredText(STORAGE_KEYS.lastSelectedCamera, activeSavedCameraId);
  renderSavedCameraDropdown();
  renderSavedCameraList();

  if (!options.skipRemoteSync) {
    void syncSavedCameraConfigsToDrive({ quiet: true }).catch(() => {});
  }
}

function findSavedCameraById(id) {
  return savedCameraConfigs.find((camera) => camera.id === id) || null;
}

function findSavedCameraForUrl(cameraUrl) {
  return savedCameraConfigs.find((camera) => camera.camera_url === cameraUrl) || null;
}

function getCurrentCameraUrl() {
  if (currentSourceType() === "ip" || currentSourceType() === "mobile") {
    return prepareSourceUrl(currentSourceType()) || getSourceInputValue(currentSourceType());
  }

  return els.cameraSelect.value === "" ? "" : `local:${els.cameraSelect.value}`;
}

function parseCameraUrl(cameraUrl) {
  const normalizedUrl = String(cameraUrl || "").trim();
  if (normalizedUrl.startsWith("local:")) {
    const cameraIndex = Number(normalizedUrl.slice("local:".length));
    return {
      source_type: "local",
      camera_index: Number.isFinite(cameraIndex) ? cameraIndex : null,
      source_url: "",
    };
  }

  return {
    source_type: normalizedUrl.includes("/video") ? "mobile" : "ip",
    camera_index: null,
    source_url: normalizedUrl,
  };
}

function getLocalCameraLabel(cameraIndex) {
  const match = Array.from(els.cameraSelect.options).find(
    (option) => option.value === String(cameraIndex),
  );
  return match ? match.textContent.replace(" (selected)", "") : `Local Camera ${cameraIndex}`;
}

function getSavedCameraMeta(camera) {
  const parsed = parseCameraUrl(camera.camera_url);
  if (parsed.source_type === "local" && parsed.camera_index !== null) {
    return getLocalCameraLabel(parsed.camera_index);
  }
  if (camera.zone_name) {
    return camera.zone_name;
  }
  return parsed.source_type === "mobile" ? "Mobile Camera" : "IP Camera";
}

function syncCameraConfigState(overrides = {}) {
  const polygonPoints =
    normalizePoints(
      overrides.polygon_points ??
        getDraftPoints() ??
        parseZonePointsInput() ??
        cameraConfigState.polygon_points,
    ) || [];
  const cameraName =
    String(overrides.camera_name ?? els.currentCameraName.value).trim() || cameraConfigState.camera_name || "";
  const cameraUrl = String(overrides.camera_url ?? getCurrentCameraUrl()).trim();
  const zoneName =
    String(overrides.zone_name ?? els.zoneName.value).trim() || getDefaultZoneName();

  cameraConfigState = {
    camera_name: cameraName,
    camera_url: cameraUrl,
    zone_name: zoneName,
    polygon_points: polygonPoints,
  };
  return cameraConfigState;
}

function updateCameraIdentity(options = {}) {
  const fallbackName = options.camera_name ?? cameraConfigState.camera_name ?? "";
  const shouldReplaceInput =
    options.forceInput ||
    (options.camera_name && !els.currentCameraName.dataset.userEdited);

  if (shouldReplaceInput) {
    els.currentCameraName.value = fallbackName;
    delete els.currentCameraName.dataset.userEdited;
  }

  const typedName = els.currentCameraName.value.trim();
  const displayName = typedName || fallbackName;
  els.cameraPageMeta.textContent = displayName || "Awaiting camera selection";
  els.homeCameraMeta.textContent = displayName || "Cam --";
  if (els.homeActiveCameraName) {
    els.homeActiveCameraName.textContent = displayName || "No camera selected";
  }
  if (els.homeActiveCameraInfo) {
    els.homeActiveCameraInfo.textContent = displayName
      ? `Zone ${els.zoneName.value.trim() || getDefaultZoneName()}`
      : savedCameraConfigs.length
        ? "Select a saved camera from the dropdown."
        : "No cameras added. Go to Saved Cameras to add one.";
  }
  syncCameraConfigState({ camera_name: typedName });
}

function renderSavedCameraDropdown() {
  if (!savedCameraConfigs.length) {
    els.homeCameraSelect.innerHTML = `<option value="">No cameras added</option>`;
    els.homeCameraSelect.disabled = true;
    if (els.homeActiveCameraName) {
      els.homeActiveCameraName.textContent = "No camera selected";
    }
    if (els.homeActiveCameraInfo) {
      els.homeActiveCameraInfo.textContent = "No cameras added. Go to Saved Cameras to add one.";
    }
    return;
  }

  const optionsHtml = [
    `<option value="">Select saved camera</option>`,
    ...savedCameraConfigs.map(
      (camera) =>
        `<option value="${esc(camera.id)}">${esc(camera.camera_name)}</option>`,
    ),
  ].join("");

  els.homeCameraSelect.innerHTML = optionsHtml;
  els.homeCameraSelect.disabled = false;
  els.homeCameraSelect.value = findSavedCameraById(activeSavedCameraId) ? activeSavedCameraId : "";
}

function getSavedCameraSourceLabel(camera) {
  const type = camera.source_type || parseCameraUrl(camera.camera_url).source_type;
  if (type === "local") return "Local Camera";
  if (type === "mobile") return "Mobile Camera";
  return "IP Camera";
}

function renderSavedCameraList() {
  if (!savedCameraConfigs.length) {
    els.savedCameraList.innerHTML = `
      <div class="savedCameraEmpty">
        <div class="savedCameraEmptyIcon"><i data-lucide="camera"></i></div>
        <div><strong>No cameras saved yet</strong></div>
        <div>Click <strong>Add Camera</strong> to connect a source and save your first camera profile.</div>
      </div>
    `;
    if (globalThis.lucide?.createIcons) globalThis.lucide.createIcons();
    return;
  }

  els.savedCameraList.innerHTML = savedCameraConfigs
    .map((camera) => {
      const activeClass = camera.id === activeSavedCameraId ? " active" : "";
      const badgeLabel = camera.id === activeSavedCameraId ? "Active" : "Saved";
      const sourceLabel = getSavedCameraSourceLabel(camera);
      const zoneLabel = camera.zone_name || "No zone";
      const pointCount = (camera.polygon_points || []).length;
      return `
        <div class="savedCameraCard${activeClass}">
          <div class="savedCardHeader">
            <div class="savedCardIcon">
              <i data-lucide="camera"></i>
            </div>
            <div class="savedCardInfo">
              <div class="savedCameraCardTitle">${esc(camera.camera_name)}</div>
              <div class="savedCameraCardMeta">${esc(sourceLabel)}</div>
            </div>
            <span class="savedCardBadge">${esc(badgeLabel)}</span>
          </div>
          <div class="savedCardDetails">
            <span class="savedCardDetail"><i data-lucide="map-pin"></i> ${esc(zoneLabel)}</span>
            <span class="savedCardDetail"><i data-lucide="pentagon"></i> ${pointCount} pts</span>
          </div>
          <div class="savedCameraCardActions">
            <button class="primary" type="button" data-camera-use="${esc(camera.id)}">Use Camera</button>
            <button class="savedCameraDelete" type="button" title="Delete saved camera" data-camera-delete="${esc(camera.id)}" aria-label="Delete ${esc(camera.camera_name)}">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 6h18"></path>
                <path d="M8 6V4h8v2"></path>
                <path d="M19 6l-1 14H6L5 6"></path>
                <path d="M10 11v6"></path>
                <path d="M14 11v6"></path>
              </svg>
            </button>
          </div>
        </div>
      `;
    })
    .join("");

  if (globalThis.lucide?.createIcons) globalThis.lucide.createIcons();
}

async function upsertSavedCamera(camera) {
  const normalized = normalizeSavedCamera(camera);
  if (!normalized) {
    return null;
  }

  const existingIndex = activeSavedCameraId
    ? savedCameraConfigs.findIndex((item) => item.id === activeSavedCameraId)
    : savedCameraConfigs.findIndex(
        (item) =>
          item.camera_url === normalized.camera_url ||
          item.camera_name.toLowerCase() === normalized.camera_name.toLowerCase(),
      );

  if (existingIndex >= 0) {
    savedCameraConfigs[existingIndex] = {
      ...savedCameraConfigs[existingIndex],
      ...normalized,
      id: savedCameraConfigs[existingIndex].id,
    };
  } else {
    savedCameraConfigs.push(normalized);
  }

  const saved =
    existingIndex >= 0 ? savedCameraConfigs[existingIndex] : savedCameraConfigs[savedCameraConfigs.length - 1];
  setActiveSavedCamera(saved.id, { skipRemoteSync: true });
  await persistSavedCameraConfigs({ quiet: true });
  return saved;
}

async function deleteSavedCamera(cameraId) {
  const deletedCamera = findSavedCameraById(cameraId);
  if (!deletedCamera) {
    return;
  }

  savedCameraConfigs = savedCameraConfigs.filter((camera) => camera.id !== cameraId);
  const wasActive = activeSavedCameraId === cameraId;

  if (wasActive) {
    if (polling) {
      await stopCamera();
    }
    activeSavedCameraId = "";
    setStoredText(STORAGE_KEYS.lastSelectedCamera, "");
    els.homeCameraSelect.value = "";
    els.currentCameraName.value = "";
    els.ipCameraUrl.value = "";
    delete els.currentCameraName.dataset.userEdited;
    resetZoneEditor("Saved camera deleted. Configure a new zone to continue.");
    updateCameraIdentity({ camera_name: "", forceInput: true });
    hideCameraBuilder("");
  }

  await persistSavedCameraConfigs({ quiet: true });
}

function updateActionButtons() {
  const builderOpen = Boolean(els.cameraBuilder && !els.cameraBuilder.hidden);
  const localActive = isLocalSource();
  const hasLocalCamera = !els.cameraSelect.disabled && els.cameraSelect.value !== "";
  const points = getDraftPoints();
  const hasValidPolygon = Boolean(points && points.length >= 3);
  const uploadPoints = getUploadDraftPoints();
  const hasValidUploadPolygon = Boolean(uploadPoints && uploadPoints.length >= 3);
  const hasUploadFile = Boolean(els.uploadVideoFile.files?.length);
  const localCameraReady =
    !localActive ||
    activeLocalCameraIndex === null ||
    Number(els.cameraSelect.value) === activeLocalCameraIndex;

  els.btnRefreshCameras.disabled = !localActive;
  els.btnSwitchCamera.disabled = !localActive || !hasLocalCamera;
  els.btnStart.disabled = !localActive || polling;
  els.btnStop.disabled = !localActive || !polling;
  els.btnClearZone.disabled = false;
  els.btnFinishDrawing.disabled = !isDrawMode() || !hasValidPolygon;
  els.btnSetZone.disabled = !builderOpen || !hasValidPolygon || !localCameraReady;
  els.btnUploadFinishDrawing.disabled = !isUploadDrawMode() || !hasValidUploadPolygon;
  els.btnAnalyzeVideo.disabled = !hasUploadFile || !hasValidUploadPolygon;
}

function setPage(page) {
  const pages = {
    home: els.pageHome,
    saved: els.pageSavedCameras,
    upload: els.pageUploadVideo,
    account: els.pageAccount,
  };
  const navs = {
    home: els.navHome,
    saved: els.navSavedCameras,
    upload: els.navUploadVideo,
    account: els.navAccount,
  };

  Object.entries(pages).forEach(([key, node]) => {
    node.classList.toggle("active", key === page);
  });
  Object.entries(navs).forEach(([key, node]) => {
    node.classList.toggle("active", key === page);
  });
}

function setFeedVisible(img, placeholder, isLive) {
  img.style.display = isLive ? "block" : "none";
  placeholder.style.display = isLive ? "none" : "grid";
}

function setPlaceholderContent(node, title, detail) {
  node.innerHTML = `<div><strong>${esc(title)}</strong><div>${esc(detail)}</div></div>`;
}

function setPreviewState(mode, detail = "") {
  if (mode === "connecting") {
    const message = detail || "Waiting for the first frame from the selected source.";
    setPlaceholderContent(els.homePlaceholder, "Connecting to camera...", message);
    setPlaceholderContent(els.cameraPlaceholder, "Connecting to camera...", message);
    return;
  }

  if (mode === "error") {
    const message = detail || "The selected camera source could not provide a frame.";
    setPlaceholderContent(els.homePlaceholder, "Camera preview unavailable", message);
    setPlaceholderContent(els.cameraPlaceholder, "Camera preview unavailable", message);
    return;
  }

  setPlaceholderContent(els.homePlaceholder, "Camera feed is idle", "Select a saved camera to load its stream and zone.");
  setPlaceholderContent(els.cameraPlaceholder, "Camera preview is idle", "Open Saved Cameras, add a camera, then test and start the stream.");
}

function setLive(isLive) {
  polling = isLive;
  els.statusPill.classList.toggle("live", isLive);
  els.statusText.textContent = isLive ? "LIVE" : "OFFLINE";

  if (isLive) {
    hasFrame = false;
    els.homeVideoFeed.removeAttribute("src");
    els.cameraVideoFeed.removeAttribute("src");
    setPreviewState("connecting");
  } else {
    hasFrame = false;
    els.homeVideoFeed.removeAttribute("src");
    els.cameraVideoFeed.removeAttribute("src");
    setPreviewState("idle");
    renderDetections([]);
  }

  setFeedVisible(els.homeVideoFeed, els.homePlaceholder, polling && hasFrame);
  setFeedVisible(els.cameraVideoFeed, els.cameraPlaceholder, polling && hasFrame);
  updateActionButtons();
}

function setModes(preprocessingEnabled, trackingEnabled) {
  els.preprocessState.textContent = preprocessingEnabled ? "ON" : "OFF";
  els.trackingState.textContent = trackingEnabled ? "ON" : "OFF";
}

function renderIdentity(user) {
  const name = user.displayName || user.email?.split("@")[0] || "User";
  const initial = name.charAt(0).toUpperCase();
  const identity = user.displayName && user.email
    ? `${user.displayName} | ${user.email}`
    : user.email || user.displayName || "Authenticated user";
  els.accountIdentity.textContent = identity;
  els.accountIdentity.className = "state ok";
  // Update navbar pill
  if (els.navAvatar) els.navAvatar.textContent = initial;
  if (els.navDisplayName) els.navDisplayName.textContent = name;
}

function renderDrive(drive) {
  driveConfigured = Boolean(drive?.configured);
  els.driveState.textContent = drive.message || "Drive status unavailable.";
  els.driveState.className = driveConfigured ? "state ok" : "state";

  if (driveConfigured) {
    els.driveConnectGroup.hidden = true;
    els.driveSyncGroup.hidden = false;
  } else if (drive?.has_credentials) {
    els.driveConnectGroup.hidden = false;
    els.driveSyncGroup.hidden = true;
  } else {
    els.driveConnectGroup.hidden = true;
    els.driveSyncGroup.hidden = true;
  }
}

function getCurrentUserProfile() {
  return {
    displayName: currentUser?.displayName || "",
    email: currentUser?.email || "",
    uid: currentUser?.uid || "",
  };
}

async function connectDrive() {
  if (!currentUser) {
    setNotice("Sign in before connecting Drive.", "err");
    return;
  }

  try {
    const token = await currentUser.getIdToken();
    window.location.assign(`/auth/drive/connect?token=${encodeURIComponent(token)}`);
  } catch (error) {
    setNotice(error.message || "Unable to connect Drive.", "err");
  }
}

function resetZoneEditor(statusText = "No zone configured for this camera.") {
  drawPoints = [];
  els.zoneMode.value = "draw";
  els.zoneName.value = "";
  els.zonePoints.value = "";
  applyZoneMode();
  setZoneState(statusText, false);
  syncCameraConfigState({ polygon_points: [], zone_name: "" });
  if (els.homeActiveCameraInfo && activeSavedCameraId) {
    els.homeActiveCameraInfo.textContent = "No saved zone loaded.";
  }
}

function applyEditorState(camera) {
  const normalized = normalizeSavedCamera(camera);
  if (!normalized) {
    return;
  }

  cameraBuilderDraftMode = false;
  drawPoints = normalized.polygon_points;
  els.currentCameraName.value = normalized.camera_name;
  delete els.currentCameraName.dataset.userEdited;
  els.zoneName.value = normalized.zone_name;
  els.zoneMode.value = "draw";
  els.zonePoints.value = JSON.stringify(drawPoints);
  applyZoneMode();
  setZoneState(
    drawPoints.length >= 3
      ? `Loaded ${normalized.zone_name} for ${normalized.camera_name}.`
      : "Saved camera loaded. Draw a zone to continue.",
    drawPoints.length >= 3,
  );
  updateCameraIdentity({ camera_name: normalized.camera_name, forceInput: true });
  syncCameraConfigState(normalized);
}

async function pushZoneToBackend(zoneName, points) {
  return readJson(
    await sessionApi("/zone", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: zoneName, points }),
    }),
  );
}

function renderCameraOptions(payload) {
  const cameras = payload.cameras || [];
  const selected = payload.selected_camera_index;
  activeLocalCameraIndex = Number.isFinite(Number(selected)) ? Number(selected) : null;

  if (!cameras.length) {
    els.cameraSelect.innerHTML = `<option value="">No cameras found</option>`;
    els.cameraSelect.disabled = true;
    updateCameraIdentity();
    updateActionButtons();
    resetZoneEditor("No zone configured for this camera.");
    renderSavedCameraDropdown();
    return;
  }

  els.cameraSelect.disabled = false;
  const optionsHtml = cameras
    .map(
      (camera) =>
        `<option value="${camera.index}">${esc(camera.label)}${camera.index === selected ? " (selected)" : ""}</option>`,
    )
    .join("");
  els.cameraSelect.innerHTML = optionsHtml;
  els.cameraSelect.value = String(selected);
  updateCameraIdentity();
  renderSavedCameraDropdown();
  renderSavedCameraList();
  updateActionButtons();
}

function renderDetections(detections) {
  if (!detections.length) {
    els.detectionsList.innerHTML = `<div class="empty">No detections in the current frame.</div>`;
    return;
  }

  els.detectionsList.innerHTML = detections
    .map((detection) => {
      const status =
        detection.zone_status === "alert"
          ? "alert"
          : detection.zone_status === "safe"
            ? "safe"
            : "neutral";
      const statusText = detection.zone_status === "no-zone" ? "No Zone" : detection.zone_status;
      return `<div class="item"><div class="itemTop"><strong>${esc(detection.label)} <span class="mono">#${esc(detection.object_id ?? "?")}</span></strong><span class="pill ${status}">${esc(statusText)}</span></div><div class="mono" style="margin-top:8px">Confidence ${Math.round((detection.confidence || 0) * 100)}% | Center [${esc(detection.center[0])}, ${esc(detection.center[1])}]</div></div>`;
    })
    .join("");
}

function renderAlerts(alerts) {
  els.alertsMeta.textContent = `${alerts.length} entries`;
  if (!alerts.length) {
    els.alertsList.innerHTML = `<div class="empty">No events logged yet.</div>`;
    latestAlertId = 0;
    return;
  }

  if (alerts[0].id && alerts[0].id !== latestAlertId) {
    latestAlertId = alerts[0].id;
  }

  els.alertsList.innerHTML = alerts
    .map(
      (alert) =>
        `<div class="item"><div class="itemTop"><strong>${esc(alert.label)} <span class="mono">#${esc(alert.object_id)}</span></strong><span class="pill ${alert.event === "alert" ? "alert" : "safe"}">${esc(alert.event)}</span></div><div class="mono" style="margin-top:8px">${esc(new Date(alert.timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }))} | Zone ${esc(alert.zone)} | ${Math.round((alert.confidence || 0) * 100)}% confidence</div></div>`,
    )
    .join("");
}

async function refreshSession() {
  try {
    const session = await readJson(await authApi("/auth/session"));
    renderIdentity(currentUser);
    renderDrive(session.drive);
    await hydrateSavedCameraConfigs(session.storage);
    setNotice("Authenticated and ready.", "ok");
  } catch (error) {
    renderIdentity(currentUser);
    renderDrive({
      configured: false,
      has_credentials: true,
      message: error.message || "Unable to load cloud sync status.",
    });
    loadSavedCameraConfigs();
    setNotice(error.message || "Unable to load cloud sync status.", "err");
  }
}

async function refreshStatus() {
  try {
    const status = await readJson(await sessionApi("/status"));
    setLive(Boolean(status.camera_running));
    setModes(Boolean(status.preprocessing_enabled), Boolean(status.tracking_enabled));
    els.fpsMeta.textContent = `${Number(status.fps || 0).toFixed(1)} FPS`;
    showError(status.last_error);
    if (status.last_error && !hasFrame) {
      setPreviewState("error", status.last_error);
    } else if (status.camera_running && !hasFrame) {
      setPreviewState("connecting");
    }
  } catch (error) {
    showError(error.message);
  } finally {
    setTimeout(refreshStatus, 2000);
  }
}

async function refreshZone() {
  try {
    renderZone(await readJson(await sessionApi("/zone")));
  } catch (error) {
    setZoneState("Unable to load zone configuration.", false);
    showError(error.message);
  }
}

async function refreshCameras() {
  try {
    const payload = await readJson(await sessionApi("/camera/options"));
    renderCameraOptions(payload);
    return payload;
  } catch (error) {
    els.cameraSelect.innerHTML = `<option value="">Unable to load cameras</option>`;
    els.cameraSelect.disabled = true;
    renderSavedCameraDropdown();
    renderSavedCameraList();
    updateActionButtons();
    showError(error.message);
    return null;
  }
}

async function pollFrame() {
  try {
    if (polling) {
      const frame = await readJson(await sessionApi("/camera/frame"));
      if (frame.frame) {
        hasFrame = true;
        const src = `data:image/jpeg;base64,${frame.frame}`;
        els.homeVideoFeed.src = src;
        setFeedVisible(els.homeVideoFeed, els.homePlaceholder, true);
        if (!cameraBuilderDraftMode) {
          els.cameraVideoFeed.src = src;
          setFeedVisible(els.cameraVideoFeed, els.cameraPlaceholder, true);
        }
      } else if (!hasFrame) {
        setPreviewState("connecting");
        setFeedVisible(els.homeVideoFeed, els.homePlaceholder, false);
        if (!cameraBuilderDraftMode) {
          setFeedVisible(els.cameraVideoFeed, els.cameraPlaceholder, false);
        }
      }
      els.fpsMeta.textContent = `${Number(frame.fps || 0).toFixed(1)} FPS`;
      renderDetections(frame.detections || []);
    }
  } catch (error) {
    showError(error.message);
  } finally {
    setTimeout(pollFrame, polling ? 90 : 300);
  }
}

async function pollAlerts() {
  try {
    const payload = await readJson(await sessionApi("/alerts?limit=40"));
    renderAlerts(payload.alerts || []);
  } catch {
    els.alertsList.innerHTML = `<div class="empty">Unable to load alert history.</div>`;
  } finally {
    setTimeout(pollAlerts, 1000);
  }
}

async function startCamera() {
  cameraBuilderDraftMode = false;
  const type = currentSourceType();
  const payload = { action: "start", source_type: type };
  if (type !== "local") {
    const url = prepareSourceUrl(type);
    if (!url) {
      showError(type === "mobile" ? "Enter a mobile stream URL before starting." : "Enter a camera URL before starting.");
      return;
    }
    payload.source_url = url;
  }
  try {
    await readJson(
      await sessionApi("/camera/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    );
    setLive(true);
    showError("");
  } catch (error) {
    showError(error.message);
  }
}

async function stopCamera() {
  try {
    await readJson(
      await sessionApi("/camera/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "stop" }),
      }),
    );
    setLive(false);
  } catch (error) {
    showError(error.message);
  }
}

function applyZoneMode() {
  if (isDrawMode()) {
    const typedPoints = parseZonePointsInput();
    if (typedPoints) {
      drawPoints = typedPoints;
    }
    els.zonePoints.disabled = true;
    els.videoZoneCanvas.style.display = "block";
    els.drawHint.style.display = "block";
    els.videoZoneCanvas.focus();
  } else {
    els.zonePoints.disabled = false;
    els.zonePoints.value = drawPoints.length ? JSON.stringify(drawPoints) : els.zonePoints.value;
    els.videoZoneCanvas.style.display = "none";
    els.drawHint.style.display = "none";
  }

  redrawCanvas();
  syncCameraConfigState();
  updateActionButtons();
}

function renderZone(zone) {
  if (cameraBuilderDraftMode && els.cameraBuilder && !els.cameraBuilder.hidden) {
    return;
  }

  if (!zone.active) {
    resetZoneEditor("No zone configured for this camera.");
    return;
  }

  drawPoints = normalizePoints(zone.points) || [];
  els.zoneName.value = zone.name || getDefaultZoneName();
  els.zonePoints.value = JSON.stringify(drawPoints);
  setZoneState(`${zone.name || "Zone"} active for this camera | ${zone.area_px} px^2`, true);
  applyZoneMode();
  if (els.homeActiveCameraInfo) {
    els.homeActiveCameraInfo.textContent = `Zone ${zone.name || "Zone"}`;
  }
  syncCameraConfigState({
    zone_name: els.zoneName.value,
    polygon_points: drawPoints,
  });
}

async function clearAlerts(options = {}) {
  try {
    await readJson(await sessionApi("/alerts", { method: "DELETE" }));
    latestAlertId = 0;
    renderAlerts([]);
    els.alertsMeta.textContent = "0 entries";
    if (!options.skipStatus) {
      await refreshStatus();
    }
  } catch (error) {
    showError(error.message);
  }
}

async function switchCamera() {
  cameraBuilderDraftMode = false;
  if (!isLocalSource()) {
    showError("Switching is currently enabled for local cameras only.");
    return;
  }

  const value = els.cameraSelect.value;
  if (value === "") {
    showError("No camera is available to select.");
    return;
  }

  try {
    await readJson(
      await sessionApi("/camera/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ camera_index: Number(value) }),
      }),
    );
    await clearAlerts({ skipStatus: true });
    await refreshCameras();
    await refreshZone();
    await refreshStatus();
    const matchedSavedCamera = findSavedCameraForUrl(`local:${value}`);
    if (matchedSavedCamera) {
      applyEditorState(matchedSavedCamera);
      setActiveSavedCamera(matchedSavedCamera.id);
    } else {
      setActiveSavedCamera("");
    }
    showError("");
  } catch (error) {
    showError(error.message);
  }
}

async function switchToSavedCamera(camera, options = {}) {
  const normalized = normalizeSavedCamera(camera);
  if (!normalized) {
    return;
  }

  if (options.navigateHome) {
    setPage("home");
  }

  const parsed = parseCameraUrl(normalized.camera_url);
  els.cameraSourceType.value = parsed.source_type;

  if (parsed.source_type === "local") {
    if (parsed.camera_index === null || !Array.from(els.cameraSelect.options).some((option) => option.value === String(parsed.camera_index))) {
      showError(`Saved camera ${normalized.camera_name} is not currently available.`);
      return;
    }
    els.cameraSelect.value = String(parsed.camera_index);
  } else {
    els.ipCameraUrl.value = normalized.camera_url;
  }

  applySourceMode();
  applyEditorState(normalized);
  setActiveSavedCamera(normalized.id);

  if (!options.startPreview && !polling) {
    showError("");
    return;
  }

  try {
    if (parsed.source_type === "local") {
      await switchCamera();
      if (options.startPreview || polling) {
        await startCamera();
      }
    } else {
      if (options.startPreview || polling) {
        await startCamera();
      }
    }

    if (normalized.polygon_points.length >= 3) {
      await pushZoneToBackend(normalized.zone_name, normalized.polygon_points);
      await refreshZone();
    }
    showError("");
  } catch (error) {
    showError(error.message);
  }
}

function validateUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" || url.protocol === "rtsp:";
  } catch {
    return false;
  }
}

async function testCameraSource() {
  cameraBuilderDraftMode = false;
  const type = currentSourceType();
  if (type === "local") {
    await refreshCameras();
    return;
  }

  const input = prepareSourceUrl(type);
  if (!input) {
    showError(type === "mobile" ? "Enter a mobile stream URL before testing." : "Enter a camera URL before testing.");
    return;
  }

  if (!validateUrl(input)) {
    showError("Invalid URL format. Check the stream address.");
    return;
  }

  showError("");
  // Actually start the camera with this source to test it
  await startCamera();
}

function renderUploadSummaryEmpty() {
  els.uploadSummary.innerHTML = `<div class="empty">No video analyzed yet.</div>`;
}

function renderUploadAlertsEmpty() {
  els.uploadAlerts.innerHTML = `<div class="empty">No events yet.</div>`;
}

function clearUploadResults(options = {}) {
  renderUploadSummaryEmpty();
  renderUploadAlertsEmpty();
  if (!options.keepStateMessage) {
    setUploadState("Upload a video, draw a fresh zone or paste polygon points, then analyze it.", false);
  }
}

function getUploadFrameSize() {
  return uploadPreviewSize.width > 0 && uploadPreviewSize.height > 0 ? uploadPreviewSize : FRAME;
}

function getUploadBounds() {
  const width = els.uploadPreviewStage.clientWidth;
  const height = els.uploadPreviewStage.clientHeight;
  const frame = getUploadFrameSize();
  const scale = Math.min(width / frame.width, height / frame.height);
  return {
    left: (width - frame.width * scale) / 2,
    top: (height - frame.height * scale) / 2,
    width: frame.width * scale,
    height: frame.height * scale,
    scale,
  };
}

function redrawUploadCanvas() {
  const canvas = els.uploadZoneCanvas;
  canvas.width = els.uploadPreviewStage.clientWidth;
  canvas.height = els.uploadPreviewStage.clientHeight;

  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!isUploadDrawMode() || !uploadPreviewSize.width || !uploadPreviewSize.height) {
    return;
  }

  const bounds = getUploadBounds();
  ctx.fillStyle = "rgba(89,242,194,.08)";
  ctx.fillRect(bounds.left, bounds.top, bounds.width, bounds.height);

  if (!uploadDrawPoints.length) {
    return;
  }

  ctx.strokeStyle = "#59f2c2";
  ctx.fillStyle = "rgba(89,242,194,.18)";
  ctx.lineWidth = 2;
  ctx.setLineDash([8, 5]);
  ctx.beginPath();

  uploadDrawPoints.forEach((point, index) => {
    const x = bounds.left + point[0] * bounds.scale;
    const y = bounds.top + point[1] * bounds.scale;
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });

  if (uploadDrawPoints.length >= 3) {
    ctx.closePath();
    ctx.fill();
  }

  ctx.stroke();
  ctx.setLineDash([]);

  uploadDrawPoints.forEach((point) => {
    const x = bounds.left + point[0] * bounds.scale;
    const y = bounds.top + point[1] * bounds.scale;
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fillStyle = "#59f2c2";
    ctx.fill();
  });
}

function resetUploadZoneEditor(statusText = "Choose a recorded video to extract a frame and draw a fresh zone.") {
  uploadDrawPoints = [];
  els.uploadZoneMode.value = "draw";
  els.uploadZoneName.value = "";
  els.uploadZonePoints.value = "";
  applyUploadZoneMode();
  setUploadState(statusText, false);
}

function clearUploadZone() {
  uploadDrawPoints = [];
  els.uploadZonePoints.value = "";
  els.uploadZoneName.value = "";
  applyUploadZoneMode();
  setUploadState("Upload zone cleared. Draw a fresh polygon or paste new polygon points.", false);
}

function applyUploadZoneMode() {
  if (isUploadDrawMode()) {
    const typedPoints = parseUploadZonePointsInput();
    if (typedPoints) {
      uploadDrawPoints = typedPoints;
    }
    els.uploadZonePoints.disabled = true;
    els.uploadZoneCanvas.style.display = uploadPreviewSize.width ? "block" : "none";
    els.uploadZoneHint.style.display = uploadPreviewSize.width ? "block" : "none";
    if (uploadPreviewSize.width) {
      els.uploadZoneCanvas.focus();
    }
  } else {
    els.uploadZonePoints.disabled = false;
    if (uploadDrawPoints.length) {
      els.uploadZonePoints.value = JSON.stringify(uploadDrawPoints);
    }
    els.uploadZoneCanvas.style.display = "none";
    els.uploadZoneHint.style.display = "none";
  }

  redrawUploadCanvas();
  updateActionButtons();
}

function finishUploadDrawing() {
  const points = normalizePoints(getUploadDraftPoints() || []);
  if (!points || points.length < 3) {
    setUploadState("Add at least 3 points before finishing the polygon.", false);
    return;
  }

  uploadDrawPoints = points;
  els.uploadZonePoints.value = JSON.stringify(uploadDrawPoints);
  setUploadState(`Polygon completed with ${uploadDrawPoints.length} points. Analyze the video when ready.`, true);
  redrawUploadCanvas();
  updateActionButtons();
}

function handleUploadCanvasClick(event) {
  if (!isUploadDrawMode() || event.button !== 0 || !uploadPreviewSize.width || !uploadPreviewSize.height) {
    return;
  }

  const rect = els.uploadZoneCanvas.getBoundingClientRect();
  const bounds = getUploadBounds();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  if (x < bounds.left || x > bounds.left + bounds.width || y < bounds.top || y > bounds.top + bounds.height) {
    return;
  }

  uploadDrawPoints.push([
    Math.round((x - bounds.left) / bounds.scale),
    Math.round((y - bounds.top) / bounds.scale),
  ]);
  els.uploadZonePoints.value = JSON.stringify(uploadDrawPoints);
  setUploadState(
    uploadDrawPoints.length >= 3
      ? `Polygon ready with ${uploadDrawPoints.length} points. Finish drawing or analyze the video.`
      : `Point ${uploadDrawPoints.length} added. Add at least ${3 - uploadDrawPoints.length} more point(s).`,
    uploadDrawPoints.length >= 3,
  );
  redrawUploadCanvas();
  updateActionButtons();
}

function handleUploadCanvasKey(event) {
  if (!isUploadDrawMode()) {
    return;
  }

  if (event.key.toLowerCase() === "r") {
    uploadDrawPoints = [];
    els.uploadZonePoints.value = "";
    setUploadState("Polygon cleared. Click on the preview to add new points.", false);
    redrawUploadCanvas();
    updateActionButtons();
  }

  if (event.key === "Escape") {
    els.uploadZoneMode.value = "manual";
    applyUploadZoneMode();
  }
}

function setUploadPreviewSource(src = "", options = {}) {
  if (!src) {
    uploadPreviewSize = { width: 0, height: 0 };
    els.uploadPreviewImage.removeAttribute("src");
    els.uploadPreviewImage.style.display = "none";
    els.uploadPreviewPlaceholder.style.display = "grid";
    setPlaceholderContent(
      els.uploadPreviewPlaceholder,
      options.title || "No upload processed yet",
      options.detail || "Choose a recorded video to extract a frame and draw a new zone.",
    );
    redrawUploadCanvas();
    updateActionButtons();
    return;
  }

  els.uploadPreviewImage.src = src;
  els.uploadPreviewImage.style.display = "block";
  els.uploadPreviewPlaceholder.style.display = "none";
}

async function loadUploadPreviewFromFile(file) {
  if (!file) {
    setUploadPreviewSource("", {
      title: "No upload processed yet",
      detail: "Choose a recorded video to extract a frame and draw a new zone.",
    });
    clearUploadResults({ keepStateMessage: true });
    resetUploadZoneEditor();
    return;
  }

  const objectUrl = URL.createObjectURL(file);
  try {
    const preview = await new Promise((resolve, reject) => {
      const video = document.createElement("video");
      video.preload = "metadata";
      video.muted = true;
      video.playsInline = true;
      video.src = objectUrl;

      video.onloadeddata = () => {
        if (!video.videoWidth || !video.videoHeight) {
          reject(new Error("Unable to extract a frame from this video."));
          return;
        }

        const frameCanvas = document.createElement("canvas");
        frameCanvas.width = video.videoWidth;
        frameCanvas.height = video.videoHeight;
        frameCanvas.getContext("2d").drawImage(video, 0, 0, video.videoWidth, video.videoHeight);
        resolve({
          width: video.videoWidth,
          height: video.videoHeight,
          src: frameCanvas.toDataURL("image/jpeg", 0.92),
        });
      };

      video.onerror = () => reject(new Error("Unable to read the selected video file."));
    });

    uploadPreviewSize = { width: preview.width, height: preview.height };
    setUploadPreviewSource(preview.src);
    clearUploadResults({ keepStateMessage: true });
    resetUploadZoneEditor(`Preview loaded for ${file.name}. Draw a fresh zone or paste polygon points.`);
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function renderUploadPreview(frameB64) {
  setUploadPreviewSource(
    frameB64 ? `data:image/jpeg;base64,${frameB64}` : "",
    frameB64
      ? {}
      : {
          title: "No upload processed yet",
          detail: "Choose a recorded video to extract a frame and draw a new zone.",
        },
  );
}

function renderUploadSummary(payload) {
  const summary = payload.summary || {};
  const labelCounts = payload.label_counts || {};
  const labelItems = Object.entries(labelCounts)
    .map(([label, count]) => `<div class="item"><strong>${esc(label)}</strong><div class="mono" style="margin-top:8px">${esc(count)} detections</div></div>`)
    .join("");

  els.uploadSummary.innerHTML = `
    <div class="item"><strong>${esc(payload.filename || "Uploaded video")}</strong><div class="mono" style="margin-top:8px">${esc(summary.frames_processed || 0)} frames processed | ${esc(summary.video_seconds || 0)}s video</div></div>
    <div class="item"><strong>Total detections</strong><div class="mono" style="margin-top:8px">${esc(summary.detections_total || 0)} objects detected</div></div>
    <div class="item"><strong>Alert events</strong><div class="mono" style="margin-top:8px">${esc(summary.alert_events || 0)} zone events</div></div>
    <div class="item"><strong>Zone used</strong><div class="mono" style="margin-top:8px">${esc(summary.zone_name || "Upload Zone")}</div></div>
    ${labelItems || `<div class="empty">No tracked objects found in the uploaded video.</div>`}
  `;
}

function renderUploadAlerts(alerts) {
  if (!alerts.length) {
    els.uploadAlerts.innerHTML = `<div class="empty">No alert events detected in this upload.</div>`;
    return;
  }

  els.uploadAlerts.innerHTML = alerts
    .map(
      (alert) =>
        `<div class="item"><div class="itemTop"><strong>${esc(alert.label)} <span class="mono">#${esc(alert.object_id)}</span></strong><span class="pill ${alert.event === "alert" ? "alert" : "safe"}">${esc(alert.event)}</span></div><div class="mono" style="margin-top:8px">${esc(alert.zone || "No Zone")} | ${Math.round((alert.confidence || 0) * 100)}% confidence</div></div>`,
    )
    .join("");
}

async function analyzeUploadedVideo() {
  const file = els.uploadVideoFile.files?.[0];
  const points = normalizePoints(getUploadDraftPoints() || []);
  const zoneName = els.uploadZoneName.value.trim() || "Upload Zone";

  if (!file) {
    setUploadState("Choose a recorded video file before analyzing.", false);
    return;
  }

  if (!points || points.length < 3) {
    setUploadState("Draw a fresh zone or paste at least 3 polygon points before analyzing.", false);
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("zone_name", zoneName);
  formData.append("zone_points", JSON.stringify(points));

  if (isUploadDrawMode()) {
    finishUploadDrawing();
  }

  setUploadState("Analyzing uploaded video...", false);
  try {
    const payload = await readJson(
      await sessionApi("/video/analyze", {
        method: "POST",
        body: formData,
      }),
    );
    renderUploadPreview(payload.preview_frame || "");
    renderUploadSummary(payload);
    renderUploadAlerts(payload.alerts || []);
    setUploadState("Video processed successfully.", true);
  } catch (error) {
    setUploadState(error.message, false);
  }
}

async function saveSnapshot() {
  try {
    setNotice("Saving current data to Google Drive...", "ok");
    await readJson(
      await authApi("/storage/snapshot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile: getCurrentUserProfile(),
          saved_cameras: savedCameraConfigs,
          last_selected_camera_id: activeSavedCameraId,
        }),
      }),
    );
    await refreshSession();
    setNotice("Saved current zone and session snapshot to Google Drive.", "ok");
  } catch (error) {
    setNotice(error.message, "err");
  }
}

async function restoreSnapshot() {
  try {
    setNotice("Restoring data from Google Drive...", "ok");
    const payload = await readJson(await authApi("/storage/restore", { method: "POST" }));
    if (payload.status === "empty") {
      setNotice("No Drive snapshot exists for this account yet.", "err");
      return;
    }
    applySavedCameraConfigs(payload.saved_cameras || [], {
      activeId: payload.last_selected_camera_id || readStoredText(STORAGE_KEYS.lastSelectedCamera, ""),
    });
    await refreshCameras();
    await refreshZone();
    await refreshStatus();
    const restoredCamera = findSavedCameraById(payload.last_selected_camera_id || "");
    if (restoredCamera) {
      await switchToSavedCamera(restoredCamera, { startPreview: false });
    }
    setNotice("Drive snapshot restored into the current session.", "ok");
  } catch (error) {
    setNotice(error.message, "err");
  }
}

function getBounds() {
  const width = els.cameraVideoStage.clientWidth;
  const height = els.cameraVideoStage.clientHeight;
  const scale = Math.min(width / FRAME.width, height / FRAME.height);
  return {
    left: (width - FRAME.width * scale) / 2,
    top: (height - FRAME.height * scale) / 2,
    width: FRAME.width * scale,
    height: FRAME.height * scale,
    scale,
  };
}

function redrawCanvas() {
  const canvas = els.videoZoneCanvas;
  canvas.width = els.cameraVideoStage.clientWidth;
  canvas.height = els.cameraVideoStage.clientHeight;

  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!isDrawMode()) {
    return;
  }

  const bounds = getBounds();
  ctx.fillStyle = "rgba(89,242,194,.08)";
  ctx.fillRect(bounds.left, bounds.top, bounds.width, bounds.height);

  if (!drawPoints.length) {
    return;
  }

  ctx.strokeStyle = "#59f2c2";
  ctx.fillStyle = "rgba(89,242,194,.18)";
  ctx.lineWidth = 2;
  ctx.setLineDash([8, 5]);
  ctx.beginPath();

  drawPoints.forEach((point, index) => {
    const x = bounds.left + point[0] * bounds.scale;
    const y = bounds.top + point[1] * bounds.scale;
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });

  if (drawPoints.length >= 3) {
    ctx.closePath();
    ctx.fill();
  }

  ctx.stroke();
  ctx.setLineDash([]);

  drawPoints.forEach((point) => {
    const x = bounds.left + point[0] * bounds.scale;
    const y = bounds.top + point[1] * bounds.scale;
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fillStyle = "#59f2c2";
    ctx.fill();
  });
}

function handleCanvasClick(event) {
  if (!isDrawMode() || event.button !== 0) {
    return;
  }

  const rect = els.videoZoneCanvas.getBoundingClientRect();
  const bounds = getBounds();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  if (x < bounds.left || x > bounds.left + bounds.width || y < bounds.top || y > bounds.top + bounds.height) {
    return;
  }

  drawPoints.push([
    Math.round((x - bounds.left) / bounds.scale),
    Math.round((y - bounds.top) / bounds.scale),
  ]);
  els.zonePoints.value = JSON.stringify(drawPoints);
  setZoneState(
    drawPoints.length >= 3
      ? `Polygon ready with ${drawPoints.length} points. Finish drawing or save the zone.`
      : `Point ${drawPoints.length} added. Add at least ${3 - drawPoints.length} more point(s).`,
    drawPoints.length >= 3,
  );
  redrawCanvas();
  syncCameraConfigState({ polygon_points: drawPoints });
  updateActionButtons();
}

function finishDrawing() {
  const points = normalizePoints(getDraftPoints() || []);
  if (!points || points.length < 3) {
    setZoneState("Add at least 3 points before finishing the polygon.", false);
    return;
  }

  drawPoints = points;
  els.zonePoints.value = JSON.stringify(drawPoints);
  setZoneState(`Polygon completed with ${drawPoints.length} points. Save Camera to store it.`, true);
  syncCameraConfigState({ polygon_points: drawPoints });
  redrawCanvas();
  updateActionButtons();
}

async function saveZone() {
  const points = getDraftPoints();
  if (!points || points.length < 3) {
    showError("A zone needs at least 3 points.");
    return;
  }

  if (
    isLocalSource() &&
    activeLocalCameraIndex !== null &&
    Number(els.cameraSelect.value) !== activeLocalCameraIndex
  ) {
    showError("Switch to the selected local camera before saving its zone.");
    return;
  }

  const cameraUrl = getCurrentCameraUrl();
  if (!cameraUrl) {
    showError("Enter a camera URL before saving the camera.");
    return;
  }

  finishDrawing();

  const cameraName = els.currentCameraName.value.trim();
  if (!cameraName) {
    showError("Enter a clean camera name before saving.");
    return;
  }
  const zoneName = els.zoneName.value.trim() || getDefaultZoneName();
  try {
    await pushZoneToBackend(zoneName, points);
    drawPoints = points;
    els.currentCameraName.value = cameraName;
    delete els.currentCameraName.dataset.userEdited;
    els.zoneName.value = zoneName;
    els.zonePoints.value = JSON.stringify(points);
    const savedCamera = await upsertSavedCamera({
      id: activeSavedCameraId || undefined,
      camera_name: cameraName,
      camera_url: cameraUrl,
      zone_name: zoneName,
      polygon_points: points,
      source_type: currentSourceType(),
    });
    if (savedCamera) {
      applyEditorState(savedCamera);
    }
    await refreshZone();
    setZoneState("Camera saved successfully.", true);
    hideCameraBuilder("Camera saved successfully.");
    showError("");
  } catch (error) {
    showError(error.message);
  }
}

async function clearZone() {
  try {
    await readJson(await sessionApi("/zone", { method: "DELETE" }));
    resetZoneEditor("No zone configured for this camera.");
    showError("");
  } catch (error) {
    showError(error.message);
  }
}

function handleCanvasKey(event) {
  if (!isDrawMode()) {
    return;
  }

  if (event.key.toLowerCase() === "r") {
    drawPoints = [];
    els.zonePoints.value = "";
    setZoneState("Polygon cleared. Click on the preview to add new points.", false);
    redrawCanvas();
    syncCameraConfigState({ polygon_points: [] });
    updateActionButtons();
  }

  if (event.key === "Escape") {
    els.zoneMode.value = "manual";
    applyZoneMode();
  }
}

function applySourceMode() {
  const type = currentSourceType();

  // Toggle input groups
  els.localSourceGroup.hidden = type !== "local";
  els.ipSourceGroup.hidden = type === "local";

  // Toggle control groups
  els.localControls.hidden = type !== "local";
  els.ipControls.hidden = type === "local";

  if (type !== "local") {
    resetZoneEditor("Load or draw a zone for this camera source.");
  }

  showError("");
  updateCameraIdentity();
  updateActionButtons();
}

async function handleSignOut() {
  try {
    await authApi("/auth/logout", { method: "POST" });
  } catch {
    // Continue with Firebase sign-out even if backend cleanup fails.
  }

  renderAlerts([]);
  renderDetections([]);
  setLive(false);

  if (auth) {
    await signOut(auth);
  }
  window.location.replace("/login");
}

async function initAuth() {
  const response = await fetch("/auth/firebase-config");
  const payload = await response.json();
  if (!payload.configured) {
    throw new Error(payload.message || "Firebase not configured.");
  }
  return getAuth(initializeApp(payload.config));
}

els.navHome.onclick = () => setPage("home");
els.navSavedCameras.onclick = () => setPage("saved");
els.navUploadVideo.onclick = () => setPage("upload");
els.navAccount.onclick = () => setPage("account");
els.btnSidebarSignOut.onclick = () => setPage("account");
els.btnSignOut.onclick = handleSignOut;
els.btnConnectDrive.onclick = (event) => {
  event.preventDefault();
  void connectDrive();
};
els.btnStart.onclick = startCamera;
els.btnStop.onclick = stopCamera;
els.btnRefreshCameras.onclick = refreshCameras;
els.btnSwitchCamera.onclick = switchCamera;
els.btnTestCamera.onclick = testCameraSource;
q("btnTestCameraIp").onclick = testCameraSource;
q("btnStartIp").onclick = startCamera;
q("btnStopIp").onclick = stopCamera;
els.btnFinishDrawing.onclick = finishDrawing;
els.btnSetZone.onclick = saveZone;
els.btnCancelCameraSetup.onclick = () => hideCameraBuilder("");
els.btnClearZone.onclick = clearZone;
els.btnHomeClearAlerts.onclick = () => clearAlerts();
els.btnAnalyzeVideo.onclick = analyzeUploadedVideo;
els.btnUploadClearAlerts.onclick = () => clearUploadResults();
els.btnUploadClearZone.onclick = clearUploadZone;
els.btnUploadFinishDrawing.onclick = finishUploadDrawing;
els.btnSaveSnapshot.onclick = saveSnapshot;
els.btnLoadSnapshot.onclick = restoreSnapshot;
els.zoneMode.onchange = applyZoneMode;
els.zonePoints.oninput = () => {
  if (!isDrawMode()) {
    const typedPoints = parseZonePointsInput();
    if (typedPoints) {
      drawPoints = typedPoints;
      redrawCanvas();
    }
  }
  syncCameraConfigState();
  updateActionButtons();
};
els.zoneName.oninput = () => {
  syncCameraConfigState();
};
els.uploadZoneMode.onchange = applyUploadZoneMode;
els.uploadZonePoints.oninput = () => {
  if (!isUploadDrawMode()) {
    const typedPoints = parseUploadZonePointsInput();
    if (typedPoints) {
      uploadDrawPoints = typedPoints;
      redrawUploadCanvas();
      setUploadState(`Polygon ready with ${typedPoints.length} points. Analyze the video when ready.`, typedPoints.length >= 3);
    } else if (els.uploadZonePoints.value.trim()) {
      setUploadState("Polygon points must be valid JSON like [[100,100],[400,100],[400,320]].", false);
    }
  }
  updateActionButtons();
};
els.uploadZoneName.oninput = () => {
  if (!els.uploadZoneName.value.trim() && getUploadDraftPoints()?.length >= 3) {
    setUploadState("Polygon ready. Add an optional zone name or analyze the video.", true);
  }
};
els.uploadVideoFile.onchange = async () => {
  try {
    await loadUploadPreviewFromFile(els.uploadVideoFile.files?.[0] || null);
  } catch (error) {
    setUploadPreviewSource("", {
      title: "Preview unavailable",
      detail: "Choose a different video file to draw a fresh zone.",
    });
    clearUploadResults({ keepStateMessage: true });
    resetUploadZoneEditor(error.message);
  }
};
els.currentCameraName.oninput = () => {
  els.currentCameraName.dataset.userEdited = "true";
  updateCameraIdentity({ camera_name: els.currentCameraName.value.trim() });
};
els.cameraSourceType.onchange = applySourceMode;
els.cameraSelect.onchange = () => {
  setActiveSavedCamera("");
  updateCameraIdentity();
  resetZoneEditor("Camera selection changed. Switch camera to apply and configure a fresh zone.");
  updateActionButtons();
};
els.homeCameraSelect.onchange = async () => {
  const camera = findSavedCameraById(els.homeCameraSelect.value);
  if (!camera) {
    setActiveSavedCamera("");
    return;
  }
  await switchToSavedCamera(camera, { startPreview: true });
};
els.ipCameraUrl.oninput = () => {
  setActiveSavedCamera("");
  updateCameraIdentity();
  updateActionButtons();
};
els.savedCameraList.onclick = async (event) => {
  const deleteButton = event.target.closest("[data-camera-delete]");
  if (deleteButton) {
    await deleteSavedCamera(deleteButton.getAttribute("data-camera-delete"));
    return;
  }

  const useButton = event.target.closest("[data-camera-use]");
  if (useButton) {
    const camera = findSavedCameraById(useButton.getAttribute("data-camera-use"));
    if (camera) {
      await switchToSavedCamera(camera, { startPreview: true, navigateHome: true });
    }
  }
};
els.btnAddCamera.onclick = startAddCameraFlow;
els.videoZoneCanvas.onmousedown = handleCanvasClick;
els.videoZoneCanvas.onkeydown = handleCanvasKey;
els.videoZoneCanvas.tabIndex = 0;
els.uploadZoneCanvas.onmousedown = handleUploadCanvasClick;
els.uploadZoneCanvas.onkeydown = handleUploadCanvasKey;
els.uploadZoneCanvas.tabIndex = 0;
els.uploadPreviewImage.onload = () => {
  if (els.uploadPreviewImage.naturalWidth && els.uploadPreviewImage.naturalHeight) {
    uploadPreviewSize = {
      width: els.uploadPreviewImage.naturalWidth,
      height: els.uploadPreviewImage.naturalHeight,
    };
  }
  redrawUploadCanvas();
  applyUploadZoneMode();
};
window.onresize = () => {
  redrawCanvas();
  redrawUploadCanvas();
};

if (window.lucide?.createIcons) {
  window.lucide.createIcons();
}

setPreviewState("idle");
resetZoneEditor();
applySourceMode();
loadSavedCameraConfigs();
renderSavedCameraDropdown();
renderSavedCameraList();
updateCameraEmptyState();
hideCameraBuilder("");
renderUploadPreview("");
clearUploadResults({ keepStateMessage: true });
resetUploadZoneEditor();

try {
  auth = await initAuth();
  onAuthStateChanged(auth, async (user) => {
    if (!user) {
      window.location.replace("/login");
      return;
    }

    currentUser = user;
    savedCameraConfigs = [];
    activeSavedCameraId = "";
    latestAlertId = 0;
    renderSavedCameraDropdown();
    renderSavedCameraList();
    renderAlerts([]);
    updateCameraEmptyState();
    renderIdentity(user);

    try {
      await refreshSession();
      await stopCamera().catch(() => {});
      cameraConfigState = createEmptyCameraState();
      setActiveSavedCamera("", { skipRemoteSync: true });
      resetZoneEditor(savedCameraConfigs.length ? "Select a saved camera from the dropdown to load its zone." : "No zone configured for this camera.");
      updateCameraIdentity({ camera_name: "", forceInput: true });
      renderDetections([]);
    } catch (error) {
      setNotice(error.message, "err");
    }

    if (!booted) {
      booted = true;
      await refreshCameras();
      refreshStatus();
      pollFrame();
      pollAlerts();
    }
  });
} catch (error) {
  showError(error.message);
  setNotice(error.message, "err");
}















