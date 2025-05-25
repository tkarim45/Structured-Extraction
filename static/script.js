document.addEventListener("DOMContentLoaded", () => {
  const pages = document.querySelectorAll(".page");
  const navLinks = document.querySelectorAll(".sidebar nav a");
  const uploadForm = document.getElementById("upload-form");
  const uploadStatus = document.getElementById("upload-status");
  const filesTableBody = document.querySelector("#files-table tbody");
  const sortBySelect = document.getElementById("sort-by");
  const filterStatusSelect = document.getElementById("filter-status");
  const filterDeadlineSelect = document.getElementById("filter-deadline");
  const resetFiltersButton = document.getElementById("reset-filters");

  // Chart contexts
  const dailyUploadsChart = document.getElementById("daily-uploads-chart").getContext("2d");
  const statusChart = document.getElementById("status-chart").getContext("2d");
  let dailyChartInstance, statusChartInstance;

  // Add navigation for Notices page
  const noticesTableBody = document.createElement("tbody");
  let noticeCompletionChartInstance;

  // Navigation
  navLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const pageId = link.getAttribute("data-page");
      pages.forEach((page) => page.classList.remove("active"));
      document.getElementById(pageId).classList.add("active");
      navLinks.forEach((l) => l.classList.remove("active"));
      link.classList.add("active");
      if (pageId === "files") {
        fetchFiles();
      } else if (pageId === "home") {
        fetchMetrics();
      } else if (pageId === "notices") {
        fetchNotices();
      }
    });
  });

  // Upload form
  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById("pdf-file");
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    uploadStatus.textContent = "Uploading...";
    try {
      const response = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      const result = await response.json();
      if (response.ok) {
        uploadStatus.textContent = `Upload started: ${result.filename}`;
        Toastify({
          text: "File upload started!",
          duration: 3000,
          style: { background: "green" },
        }).showToast();
        // Switch to Files tab and refresh
        document.querySelector('.sidebar nav a[data-page="files"]').click();
        fetchFiles();
      } else {
        uploadStatus.textContent = `Error: ${result.error}`;
        Toastify({
          text: `Error: ${result.error}`,
          duration: 3000,
          style: { background: "red" },
        }).showToast();
      }
    } catch (error) {
      uploadStatus.textContent = `Error: ${error.message}`;
      Toastify({
        text: `Error: ${error.message}`,
        duration: 3000,
        style: { background: "red" },
      }).showToast();
    }
  });

  // Fetch and display metrics
  async function fetchMetrics() {
    try {
      const response = await fetch("/api/metrics");
      const metrics = await response.json();
      document.getElementById("daily-avg").textContent = metrics.daily_avg_uploads;
      document.getElementById("weekly-uploads").textContent = metrics.weekly_uploads;
      document.getElementById("total-uploads").textContent = metrics.total_uploads;
      document.getElementById("unique-docs").textContent = metrics.unique_documents;

      // Destroy existing charts if they exist
      if (dailyChartInstance) dailyChartInstance.destroy();
      if (statusChartInstance) statusChartInstance.destroy();

      // Daily Uploads Bar Chart
      dailyChartInstance = new Chart(dailyUploadsChart, {
        type: "bar",
        data: {
          labels: Object.keys(metrics.daily_uploads),
          datasets: [
            {
              label: "Uploads",
              data: Object.values(metrics.daily_uploads),
              backgroundColor: "rgba(75, 192, 192, 0.2)",
              borderColor: "rgba(75, 192, 192, 1)",
              borderWidth: 1,
            },
          ],
        },
        options: {
          scales: {
            y: { beginAtZero: true, title: { display: true, text: "Number of Uploads" } },
            x: { title: { display: true, text: "Date" } },
          },
          plugins: { legend: { display: false } },
        },
      });

      // Status Distribution Pie Chart
      statusChartInstance = new Chart(statusChart, {
        type: "pie",
        data: {
          labels: ["Processing", "Completed", "Failed"],
          datasets: [
            {
              data: [metrics.status_distribution.Processing, metrics.status_distribution.Completed, metrics.status_distribution.Failed],
              backgroundColor: ["#FFCE56", "#36A2EB", "#FF6384"],
              hoverOffset: 4,
            },
          ],
        },
        options: {
          plugins: {
            legend: { position: "bottom" },
            title: { display: true, text: "File Status Distribution" },
          },
        },
      });
    } catch (error) {
      console.error("Error fetching metrics:", error);
    }
  }

  // Fetch and display files
  async function fetchFiles() {
    try {
      const response = await fetch("/api/files");
      const files = await response.json();
      renderFiles(files);
    } catch (error) {
      console.error("Error fetching files:", error);
      Toastify({
        text: `Error fetching files: ${error.message}`,
        duration: 3000,
        style: { background: "red" },
      }).showToast();
    }
  }

  function renderFiles(files) {
    let filteredFiles = [...files];

    // Apply filters
    const statusFilter = filterStatusSelect.value;
    const deadlineFilter = filterDeadlineSelect.value;
    if (statusFilter) {
      filteredFiles = filteredFiles.filter((file) => file.status === statusFilter);
    }
    if (deadlineFilter) {
      filteredFiles = filteredFiles.filter((file) => file.filename.includes(deadlineFilter));
    }

    // Apply sorting
    const sortBy = sortBySelect.value;
    if (sortBy) {
      filteredFiles.sort((a, b) => {
        if (sortBy === "document_id") {
          return a.document_id.localeCompare(b.document_id);
        } else if (sortBy === "status") {
          return a.status.localeCompare(b.status);
        }
        return 0;
      });
    }

    filesTableBody.innerHTML = "";
    filteredFiles.forEach((file, idx) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${file.notice_id || ""}</td>
        <td>${file.document_id}</td>
        <td>${file.filename}</td>
        <td>${file.upload_date}</td>
        <td>${(file.size / 1024).toFixed(2)}</td>
        <td>${file.status}</td>
        <td>${file.approval_status || ""}</td>
        <td><a href="/file/${file.filename}" class="view-btn">View</a></td>
      `;
      filesTableBody.appendChild(row);
    });
  }

  // Filter and sort handlers
  sortBySelect.addEventListener("change", fetchFiles);
  filterStatusSelect.addEventListener("change", fetchFiles);
  filterDeadlineSelect.addEventListener("change", fetchFiles);
  resetFiltersButton.addEventListener("click", () => {
    sortBySelect.value = "";
    filterStatusSelect.value = "";
    filterDeadlineSelect.value = "";
    fetchFiles();
  });

  // Initial fetch
  fetchMetrics();

  // Fetch and display notices
  async function fetchNotices() {
    try {
      const response = await fetch("/api/notices");
      const notices = await response.json();
      renderNotices(notices);
      renderNoticeCompletionChart(notices);
    } catch (error) {
      Toastify({ text: `Error fetching notices: ${error.message}`, duration: 3000, style: { background: "red" } }).showToast();
    }
  }

  function renderNotices(notices) {
    const table = document.getElementById("notices-table");
    const tbody = table.querySelector("tbody");
    tbody.innerHTML = "";
    notices.forEach((notice) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${notice.notice_id}</td>
        <td>
          <select class="notice-status-select">
            <option value="Pending Approval" ${notice.status === "Pending Approval" ? "selected" : ""}>Pending Approval</option>
            <option value="Approved" ${notice.status === "Approved" ? "selected" : ""}>Approved</option>
            <option value="Rejected" ${notice.status === "Rejected" ? "selected" : ""}>Rejected</option>
          </select>
        </td>
        <td>${notice.last_updated}</td>
        <td>${notice.summary || ""}</td>
        <td>${notice.action_item || ""}</td>
        <td><button class="approve-notice-btn" data-notice-id="${notice.notice_id}">Update</button></td>
      `;
      tbody.appendChild(row);
    });
    // Add event listeners for approve buttons
    document.querySelectorAll(".approve-notice-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const noticeId = btn.dataset.noticeId;
        const status = btn.parentElement.parentElement.querySelector(".notice-status-select").value;
        try {
          const response = await fetch(`/api/approve_notice/${noticeId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status }),
          });
          const data = await response.json();
          if (response.ok) {
            Toastify({ text: "Notice status updated!", duration: 2000, style: { background: "green" } }).showToast();
            fetchNotices();
          } else {
            Toastify({ text: `Error: ${data.error}`, duration: 3000, style: { background: "red" } }).showToast();
          }
        } catch (error) {
          Toastify({ text: `Error: ${error.message}`, duration: 3000, style: { background: "red" } }).showToast();
        }
      });
    });
  }

  function renderNoticeCompletionChart(notices) {
    const ctx = document.getElementById("notice-completion-chart").getContext("2d");
    const completed = notices.filter((n) => n.status === "Approved").length;
    const notCompleted = notices.length - completed;
    if (noticeCompletionChartInstance) noticeCompletionChartInstance.destroy();
    noticeCompletionChartInstance = new Chart(ctx, {
      type: "pie",
      data: {
        labels: ["Completed", "Not Completed"],
        datasets: [
          {
            data: [completed, notCompleted],
            backgroundColor: ["#059669", "#FF6384"],
            hoverOffset: 4,
          },
        ],
      },
      options: {
        plugins: {
          legend: { position: "bottom" },
          title: { display: true, text: "Notice Completion" },
        },
      },
    });
  }
});
