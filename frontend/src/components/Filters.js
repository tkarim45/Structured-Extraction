import React from "react";

const Filters = ({ onFilterChange }) =>
  React.createElement(
    "div",
    { className: "flex space-x-4 mb-6" },
    React.createElement(
      "select",
      {
        onChange: (e) => onFilterChange("sort", e.target.value),
        className: "p-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary",
      },
      React.createElement("option", { value: "" }, "Sort By"),
      React.createElement("option", { value: "id" }, "ID"),
      React.createElement("option", { value: "action" }, "Action")
    ),
    React.createElement(
      "select",
      {
        onChange: (e) => onFilterChange("status", e.target.value),
        className: "p-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary",
      },
      React.createElement("option", { value: "" }, "Filter by Status"),
      React.createElement("option", { value: "pending" }, "Pending"),
      React.createElement("option", { value: "completed" }, "Completed")
    ),
    React.createElement(
      "select",
      {
        onChange: (e) => onFilterChange("action", e.target.value),
        className: "p-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary",
      },
      React.createElement("option", { value: "" }, "Filter by Action"),
      React.createElement("option", { value: "review" }, "Review"),
      React.createElement("option", { value: "approve" }, "Approve")
    )
  );

export default Filters;
