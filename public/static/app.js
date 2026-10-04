// Global state
let currentVideoData = null;
let selectedResolution = "best";
let selectedFormatType = "video";
let selectedAudioFormat = "mp3";
let selectedAudioQuality = "320";
let activeEventSource = null;
let lastDownloadedFilename = "";

// DOM Elements
const urlInput = document.getElementById("url-input");
const btnPaste = document.getElementById("btn-paste");
const btnAnalyze = document.getElementById("btn-analyze");
const alertBanner = document.getElementById("alert-banner");
const alertText = document.getElementById("alert-text");
const alertClose = document.getElementById("alert-close");

// Video Preview Elements
const videoCard = document.getElementById("video-card");
const videoThumb = document.getElementById("video-thumb");
const videoDuration = document.getElementById("video-duration");
const videoQualityTag = document.getElementById("video-quality-tag");
const videoTitle = document.getElementById("video-title");
const videoChannel = document.getElementById("video-channel");
const videoViews = document.getElementById("video-views");
const resolutionGrid = document.getElementById("resolution-grid");
const selectContainer = document.getElementById("select-container");
const checkSubs = document.getElementById("check-subs");
const checkThumb = document.getElementById("check-thumb");
const btnStartDownload = document.getElementById("btn-start-download");

// Tabs
const tabVideo = document.getElementById("tab-video");
const tabAudio = document.getElementById("tab-audio");
const panelVideo = document.getElementById("panel-video");
const panelAudio = document.getElementById("panel-audio");

// Progress Elements
const progressCard = document.getElementById("progress-card");
const progressFilename = document.getElementById("progress-filename");
const progressStage = document.getElementById("progress-stage");
const progressPercent = document.getElementById("progress-percent");
const progressBarFill = document.getElementById("progress-bar-fill");
const statSpeed = document.getElementById("stat-speed");
const statDownloaded = document.getElementById("stat-downloaded");
const statTotal = document.getElementById("stat-total");
const statEta = document.getElementById("stat-eta");
const progressSuccessActions = document.getElementById("progress-success-actions");
const btnPlayDownloaded = document.getElementById("btn-play-downloaded");
const btnShowFolderDownloaded = document.getElementById("btn-show-folder-downloaded");

// History & Folders
const btnOpenFolder = document.getElementById("btn-open-folder");
const btnRefreshHistory = document.getElementById("btn-refresh-history");
const historyList = document.getElementById("history-list");
const historyEmpty = document.getElementById("history-empty");
const historyCount = document.getElementById("history-count");

// Helper: Show Alert
function showAlert(message) {
  alertText.textContent = message;
  alertBanner.classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function hideAlert() {
  alertBanner.classList.add("hidden");
}

alertClose.addEventListener("click", hideAlert);

// Paste button handler
btnPaste.addEventListener("click", async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (text) {
      urlInput.value = text.trim();
      analyzeUrl();
    }
  } catch (err) {
    showAlert("Không thể tự động đọc clipboard. Hãy nhấn Ctrl+V để dán link!");
  }
});

// Analyze on Enter key
urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    analyzeUrl();
  }
});

btnAnalyze.addEventListener("click", analyzeUrl);

async function analyzeUrl() {
  const url = urlInput.value.trim();
  if (!url) {
    showAlert("Vui lòng dán link YouTube cần tải!");
    return;
  }

  hideAlert();
  const btnText = btnAnalyze.querySelector(".btn-text");
  const btnLoader = btnAnalyze.querySelector(".btn-loader");

  btnText.classList.add("hidden");
  btnLoader.classList.remove("hidden");
  btnAnalyze.disabled = true;

  try {
    const response = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Không thể phân tích video này.");
    }

    currentVideoData = data;
    renderVideoInfo(data);
  } catch (err) {
    let msg = err.message || "Đã xảy ra lỗi.";
    if (msg.includes("confirm you’re not a bot") || msg.includes("Sign in to confirm") || msg.includes("bot")) {
      msg = "YouTube đang tạm khóa IP Cloud (Vercel) để kiểm tra bot. Bạn hãy nháy đúp file run.bat để chạy trực tiếp trên máy - sẽ tải siêu tốc và không bao giờ bị chặn!";
    }
    showAlert(msg);
  } finally {
    btnText.classList.remove("hidden");
    btnLoader.classList.add("hidden");
    btnAnalyze.disabled = false;
  }
}

function renderVideoInfo(data) {
  videoThumb.src = data.thumbnail || "";
  videoDuration.textContent = data.duration_str || "00:00";
  videoTitle.textContent = data.title || "Video không có tiêu đề";
  videoChannel.textContent = data.uploader || "YouTube";
  videoViews.textContent = data.view_count || "0";

  // Max quality badge
  const resolutions = data.resolutions || [];
  if (resolutions.length > 0) {
    const highest = resolutions[0];
    videoQualityTag.textContent = `${highest.height}p ${highest.fps > 30 ? highest.fps + 'fps' : ''} ${highest.dynamic_range !== 'SDR' ? highest.dynamic_range : ''}`.trim();
    videoQualityTag.classList.remove("hidden");
  } else {
    videoQualityTag.classList.add("hidden");
  }

  // Populate resolution cards
  resolutionGrid.innerHTML = "";

  // Card: Best Available
  const bestCard = document.createElement("div");
  bestCard.className = "res-card active";
  bestCard.dataset.res = "best";
  bestCard.innerHTML = `
    <div class="res-title">Tốt nhất (Max)</div>
    <div class="res-desc">Chất lượng cao nhất</div>
  `;
  bestCard.addEventListener("click", () => selectResCard(bestCard, "best"));
  resolutionGrid.appendChild(bestCard);
  selectedResolution = "best";

  resolutions.forEach((r) => {
    const card = document.createElement("div");
    card.className = "res-card";
    card.dataset.res = r.height.toString();
    const fpsBadge = r.fps > 30 ? ` ${r.fps}fps` : '';
    const hdrBadge = r.dynamic_range !== 'SDR' ? ` ${r.dynamic_range}` : '';
    card.innerHTML = `
      <div class="res-title">${r.height}p${fpsBadge}</div>
      <div class="res-desc">${r.filesize_str || r.label}${hdrBadge}</div>
    `;
    card.addEventListener("click", () => selectResCard(card, r.height.toString()));
    resolutionGrid.appendChild(card);
  });

  videoCard.classList.remove("hidden");
  videoCard.scrollIntoView({ behavior: "smooth", block: "start" });
}

function selectResCard(cardElement, resValue) {
  resolutionGrid.querySelectorAll(".res-card").forEach(c => c.classList.remove("active"));
  cardElement.classList.add("active");
  selectedResolution = resValue;
}

// Tab Switching
tabVideo.addEventListener("click", () => {
  tabVideo.classList.add("active");
  tabAudio.classList.remove("active");
  panelVideo.classList.remove("hidden");
  panelAudio.classList.add("hidden");
  selectedFormatType = "video";
});

tabAudio.addEventListener("click", () => {
  tabAudio.classList.add("active");
  tabVideo.classList.remove("active");
  panelAudio.classList.remove("hidden");
  panelVideo.classList.add("hidden");
  selectedFormatType = "audio";
});

// Audio format card selection
document.querySelectorAll("#panel-audio .res-card").forEach(card => {
  card.addEventListener("click", () => {
    document.querySelectorAll("#panel-audio .res-card").forEach(c => c.classList.remove("active"));
    card.classList.add("active");
    selectedAudioFormat = card.dataset.audioFmt;
    selectedAudioQuality = card.dataset.audioQuality;
  });
});

// Start Download
btnStartDownload.addEventListener("click", async () => {
  if (!currentVideoData) return;

  hideAlert();
  btnStartDownload.disabled = true;

  const payload = {
    url: currentVideoData.webpage_url,
    format_type: selectedFormatType,
    resolution: selectedResolution,
    container: selectContainer.value,
    audio_format: selectedAudioFormat,
    audio_quality: selectedAudioQuality,
    download_subs: checkSubs.checked,
    download_thumbnail: checkThumb.checked
  };

  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Không thể khởi tạo tải xuống.");
    }

    startTrackingProgress(data.task_id);
  } catch (err) {
    showAlert(err.message);
    btnStartDownload.disabled = false;
  }
});

// SSE Real-time Progress Tracking
function startTrackingProgress(taskId) {
  if (activeEventSource) {
    activeEventSource.close();
  }

  // Reset Progress UI
  progressCard.classList.remove("hidden");
  progressSuccessActions.classList.add("hidden");
  progressBarFill.style.width = "0%";
  progressPercent.textContent = "0%";
  statSpeed.textContent = "0 MB/s";
  statDownloaded.textContent = "0 MB";
  statTotal.textContent = "...";
  statEta.textContent = "...";
  progressFilename.textContent = currentVideoData?.title || "Đang tải video...";
  progressStage.textContent = "Đang kết nối yt-dlp & chuẩn bị luồng dữ liệu...";
  progressCard.scrollIntoView({ behavior: "smooth", block: "nearest" });

  activeEventSource = new EventSource(`/api/progress/${taskId}`);

  activeEventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    const percent = Math.min(Math.max(data.percent || 0, 0), 100);
    progressBarFill.style.width = `${percent}%`;
    progressPercent.textContent = `${percent}%`;

    if (data.stage) progressStage.textContent = data.stage;
    if (data.speed) statSpeed.textContent = data.speed;
    if (data.downloaded) statDownloaded.textContent = data.downloaded;
    if (data.total) statTotal.textContent = data.total;
    if (data.eta) statEta.textContent = data.eta;
    if (data.filename) {
      progressFilename.textContent = data.filename;
      lastDownloadedFilename = data.filename;
    }

    if (data.status === "completed") {
      activeEventSource.close();
      btnStartDownload.disabled = false;
      progressBarFill.style.width = "100%";
      progressPercent.textContent = "100%";
      progressStage.textContent = "Đã hoàn thành! Đang tự động lưu file về máy bạn...";
      progressSuccessActions.classList.remove("hidden");
      
      const fileToSave = data.filename || lastDownloadedFilename;
      if (fileToSave) {
        lastDownloadedFilename = fileToSave;
        triggerBrowserDownload(fileToSave);
      }
      loadHistory();
    } else if (data.status === "error") {
      activeEventSource.close();
      btnStartDownload.disabled = false;
      showAlert(`Lỗi trong quá trình tải: ${data.error_msg || "Không rõ nguyên nhân"}`);
    }
  };

  activeEventSource.onerror = () => {
    activeEventSource.close();
    btnStartDownload.disabled = false;
  };
}

// Function to trigger browser native download dialog / Save As
function triggerBrowserDownload(filename) {
  if (!filename) return;
  const decoded = decodeURIComponent(filename);
  const downloadUrl = `/api/download-file/${encodeURIComponent(decoded)}`;
  const a = document.createElement("a");
  a.href = downloadUrl;
  a.download = decoded;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
  }, 1000);
}

// Re-download Last Processed File
btnPlayDownloaded.addEventListener("click", () => {
  if (lastDownloadedFilename) {
    triggerBrowserDownload(lastDownloadedFilename);
  }
});

btnShowFolderDownloaded.addEventListener("click", () => {
  showAlert("File đã tải về thiết bị của bạn! Nhấn Ctrl + J trên trình duyệt (hoặc kiểm tra thư mục Downloads) để xem file.");
});

// Download History & File System Operations
async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    const data = await res.json();
    const files = data.files || [];

    historyCount.textContent = files.length;
    if (files.length === 0) {
      historyEmpty.classList.remove("hidden");
      historyList.innerHTML = "";
      return;
    }

    historyEmpty.classList.add("hidden");
    historyList.innerHTML = "";

    files.forEach((file) => {
      const item = document.createElement("div");
      item.className = "history-item";

      const ext = file.ext || "mp4";
      const isAudio = ["mp3", "m4a", "wav", "flac"].includes(ext);

      item.innerHTML = `
        <div class="file-info">
          <span class="file-ext-badge ${isAudio ? 'ext-mp3' : ''}">${ext}</span>
          <div class="file-name-meta">
            <span class="file-name" title="${file.name}">${file.name}</span>
            <span class="file-meta-text">${file.size_str} • ${file.modified_str}</span>
          </div>
        </div>
        <div class="file-actions">
          <button class="btn-file-action" title="Tải file về máy" onclick="triggerBrowserDownload('${encodeURIComponent(file.name)}')">
            <i class="fa-solid fa-download"></i>
          </button>
          <button class="btn-file-action delete" title="Xóa file khỏi server" onclick="deleteSpecificFile('${encodeURIComponent(file.name)}')">
            <i class="fa-solid fa-trash-can"></i>
          </button>
        </div>
      `;
      historyList.appendChild(item);
    });
  } catch (err) {
    console.error("Lỗi tải lịch sử file:", err);
  }
}

async function deleteSpecificFile(encodedName) {
  const filename = decodeURIComponent(encodedName);
  if (!confirm(`Bạn có chắc muốn xóa file "${filename}"?`)) return;

  try {
    const res = await fetch("/api/delete-file", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename })
    });
    if (res.ok) {
      loadHistory();
    } else {
      const data = await res.json();
      throw new Error(data.detail);
    }
  } catch (err) {
    showAlert(`Không thể xóa file: ${err.message}`);
  }
}

// Initial hooks
btnOpenFolder.addEventListener("click", () => {
  document.querySelector(".history-section")?.scrollIntoView({ behavior: "smooth" });
});
btnRefreshHistory.addEventListener("click", loadHistory);

// Load history on start
document.addEventListener("DOMContentLoaded", () => {
  loadHistory();
});
