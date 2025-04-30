import React, { useState, useEffect } from "react";
import axios from "axios";
import Filters from "./Filters";

const FileViewer = () => {
  const [files, setFiles] = useState([]);
  const [sort, setSort] = useState("");
  const [action, setAction] = useState("");

  useEffect(() => {
    axios
      .get("http://localhost:8000/files", { params: { sort, action } }) // Removed status
      .then((response) => setFiles(response.data))
      .catch((error) => console.error("Error fetching files:", error));
  }, [sort, action]);

  const handleUpdate = (id, field, value) => {
    axios
      .put(`http://localhost:8000/files/${id}`, { [field]: value })
      .then(() => {
        setFiles(files.map((file) => (file.id === id ? { ...file, [field]: value } : file)));
      })
      .catch((error) => console.error("Error updating file:", error));
  };

  return React.createElement(
    "div",
    { className: "container mx-auto" },
    React.createElement(Filters, {
      sort,
      setSort,
      action,
      setAction,
    }),
    React.createElement(
      "table",
      { className: "min-w-full bg-white" },
      React.createElement(
        "thead",
        null,
        React.createElement(
          "tr",
          null,
          ["ID", "Chapter", "Section No.", "Section", "Sub-Section", "Summary", "Action Item", "Deadline", "Role Assigned To"].map((header) => React.createElement("th", { key: header, className: "py-2" }, header))
        )
      ),
      React.createElement(
        "tbody",
        null,
        files.map((file) =>
          React.createElement(
            "tr",
            { key: file.id },
            React.createElement("td", { className: "border px-4 py-2" }, file.id),
            React.createElement("td", { className: "border px-4 py-2" }, file.chapter || ""),
            React.createElement("td", { className: "border px-4 py-2" }, file.section_no || ""),
            React.createElement("td", { className: "border px-4 py-2" }, file.section || ""),
            React.createElement("td", { className: "border px-4 py-2" }, file.sub_section || ""),
            React.createElement("td", { className: "border px-4 py-2" }, file.summary || ""),
            React.createElement("td", { className: "border px-4 py-2" }, file.action_item || ""),
            React.createElement("td", { className: "border px-4 py-2" }, file.deadline || ""),
            React.createElement(
              "td",
              { className: "border px-4 py-2" },
              React.createElement("input", {
                type: "text",
                value: file.role_assigned_to || "", // Handle None
                onChange: (e) => handleUpdate(file.id, "role_assigned_to", e.target.value),
                className: "border rounded p-1",
              })
            )
          )
        )
      )
    )
  );
};

export default FileViewer;
