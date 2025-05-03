document.addEventListener("DOMContentLoaded", () => {
  const navLinks = document.querySelectorAll(".sidebar nav a");
  const pages = document.querySelectorAll(".page");
  const uploadForm = document.getElementById("upload-form");
  const uploadStatus = document.getElementById("upload-status");
  const sortBy = document.getElementById("sort-by");
  const filterStatus = document.getElementById("filter-status");
  const filterDeadline = document.getElementById("filter-deadline");
  const resetFilters = document.getElementById("reset-filters");
  let filesData = [];

  // Page navigation
  navLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const pageId = link.dataset.page;

      navLinks.forEach((l) => l.classList.remove("active"));
      link.classList.add("active");

      pages.forEach((page) => page.classList.remove("active"));
      const targetPage = document.getElementById(pageId);
      targetPage.classList.add("active");

      if (pageId === "files") {
        loadFiles();
      } else if (pageId === "home") {
        loadMetrics();
      }
    });
  });

  // Upload form
  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData();
    const fileInput = document.getElementById("pdf-file");

    formData.append("file", fileInput.files[0]);

    try {
      uploadStatus.textContent = "Uploading...";
      const response = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      const data = await response.json();

      if (response.ok) {
        uploadStatus.textContent = `Success: ${data.message}`;
        uploadForm.reset();
        pollFileStatus(data.csv_path);
      } else {
        uploadStatus.textContent = `Error: ${data.error}`;
      }
    } catch (error) {
      uploadStatus.textContent = `Error: Failed to upload file - ${error.message}`;
      console.error("Upload error:", error);
    }
  });

  // Poll file status
  function pollFileStatus(filename) {
    const interval = setInterval(async () => {
      try {
        const response = await fetch("/api/files");
        const files = await response.json();
        const file = files.find((f) => f.filename === filename);
        if (file && file.status !== "Processing") {
          clearInterval(interval);
          loadFiles();
        }
      } catch (error) {
        console.error("Error polling file status:", error);
      }
    }, 2000);
  }

  // Load metrics
  async function loadMetrics() {
    try {
      const response = await fetch("/api/metrics");
      const data = await response.json();

      document.getElementById("daily-avg").textContent = data.daily_avg_uploads;
      document.getElementById("weekly-uploads").textContent = data.weekly_uploads;
      document.getElementById("total-uploads").textContent = data.total_uploads;
      document.getElementById("unique-docs").textContent = data.unique_documents;
    } catch (error) {
      console.error("Error loading metrics:", error);
    }
  }

  // Load files
  async function loadFiles() {
    try {
      const response = await fetch("/api/files");
      filesData = await response.json();
      renderFiles(filesData);
    } catch (error) {
      console.error("Error loading files:", error);
    }
  }

  // Render files with filters
  function renderFiles(files) {
    const tbody = document.querySelector("#files-table tbody");
    tbody.innerHTML = "";

    files.forEach((file) => {
      const row = document.createElement("tr");
      row.innerHTML = `
              <td>${file.document_id}</td>
              <td>${file.filename}</td>
              <td>${file.upload_date}</td>
              <td>${(file.size / 1024).toFixed(2)}</td>
              <td class="status-${file.status.toLowerCase()}">${file.status}</td>
              <td><a href="/file/${file.filename}" class="view-btn" ${file.status !== "Completed" ? "disabled" : ""}>View</a></td>
          `;
      tbody.appendChild(row);
    });
  }

  // Filter and sort
  function applyFilters() {
    let filteredFiles = [...filesData];

    // Filter by status
    const statusFilter = filterStatus.value;
    if (statusFilter) {
      filteredFiles = filteredFiles.filter((file) => file.status === statusFilter);
    }

    // Filter by deadline (assuming Effective_Date is used)
    const deadlineFilter = filterDeadline.value;
    if (deadlineFilter) {
      filteredFiles = filteredFiles.filter((file) => file.status === "Completed");
    }

    // Sort
    const sortValue = sortBy.value;
    if (sortValue) {
      filteredFiles.sort((a, b) => {
        if (sortValue === "document_id") {
          return a.document_id.localeCompare(b.document_id);
        } else if (sortValue === "status") {
          return a.status.localeCompare(b.status);
        }
        return 0;
      });
    }

    renderFiles(filteredFiles);
  }

  // Filter and sort listeners
  sortBy.addEventListener("change", applyFilters);
  filterStatus.addEventListener("change", applyFilters);
  filterDeadline.addEventListener("change", applyFilters);
  resetFilters.addEventListener("click", () => {
    sortBy.value = "";
    filterStatus.value = "";
    filterDeadline.value = "";
    renderFiles(filesData);
  });

  // Initial load
  loadMetrics();
});
