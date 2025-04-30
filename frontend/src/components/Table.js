import React, { useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";

const Table = ({ data }) => {
  const [editableData, setEditableData] = useState(data);

  const handleEdit = (id, field, value) => {
    setEditableData((prev) => prev.map((item) => (item.id === id ? { ...item, [field]: value } : item)));
    axios.put(`http://localhost:8000/files/${id}`, { [field]: value }).catch((error) => console.error("Error updating file:", error));
  };

  return React.createElement(
    "div",
    { className: "overflow-x-auto" },
    React.createElement(
      "table",
      { className: "min-w-full bg-white shadow-md rounded-lg" },
      React.createElement(
        "thead",
        null,
        React.createElement(
          "tr",
          { className: "bg-primary text-white" },
          ["Chapter", "Section No.", "Section", "Sub-Section", "Summary", "Action Item", "Deadline", "Role Assigned To"].map((header) => React.createElement("th", { key: header, className: "p-4 text-left" }, header))
        )
      ),
      React.createElement(
        "tbody",
        null,
        editableData.map((item) =>
          React.createElement(
            "tr",
            { key: item.id, className: "border-b hover:bg-secondary" },
            React.createElement("td", { className: "p-4" }, React.createElement(Link, { to: `/file/${item.id}`, className: "text-primary" }, item.chapter)),
            React.createElement("td", { className: "p-4" }, item.section_no),
            React.createElement("td", { className: "p-4" }, item.section),
            React.createElement("td", { className: "p-4" }, item.sub_section),
            React.createElement("td", { className: "p-4" }, item.summary),
            React.createElement("td", { className: "p-4" }, item.action_item),
            React.createElement(
              "td",
              { className: "p-4" },
              React.createElement("input", {
                type: "date",
                value: item.deadline,
                onChange: (e) => handleEdit(item.id, "deadline", e.target.value),
                className: "p-2 border rounded-lg",
              })
            ),
            React.createElement(
              "td",
              { className: "p-4" },
              React.createElement("input", {
                type: "text",
                value: item.role_assigned_to,
                onChange: (e) => handleEdit(item.id, "role_assigned_to", e.target.value),
                className: "p-2 border rounded-lg",
              })
            )
          )
        )
      )
    )
  );
};

export default Table;
