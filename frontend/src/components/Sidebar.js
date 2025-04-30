import React from "react";
import { NavLink } from "react-router-dom";
import { HomeIcon, ArrowUpTrayIcon, DocumentTextIcon } from "@heroicons/react/24/outline";

const Sidebar = () =>
  React.createElement(
    "div",
    { className: "w-64 bg-white shadow-md h-screen p-6" },
    React.createElement("h1", { className: "text-2xl font-bold text-primary mb-8" }, "File Dashboard"),
    React.createElement(
      "nav",
      null,
      React.createElement(
        NavLink,
        {
          to: "/",
          className: ({ isActive }) => `flex items-center p-2 mb-2 rounded-lg ${isActive ? "bg-primary text-white" : "text-gray-700 hover:bg-secondary"}`,
        },
        React.createElement(HomeIcon, { className: "w-5 h-5 mr-2" }),
        "Home"
      ),
      React.createElement(
        NavLink,
        {
          to: "/upload",
          className: ({ isActive }) => `flex items-center p-2 mb-2 rounded-lg ${isActive ? "bg-primary text-white" : "text-gray-700 hover:bg-secondary"}`,
        },
        React.createElement(ArrowUpTrayIcon, { className: "w-5 h-5 mr-2" }),
        "Upload File"
      ),
      React.createElement(
        NavLink,
        {
          to: "/",
          className: ({ isActive }) => `flex items-center p-2 mb-2 rounded-lg ${isActive ? "bg-primary text-white" : "text-gray-700 hover:bg-secondary"}`,
        },
        React.createElement(DocumentTextIcon, { className: "w-5 h-5 mr-2" }),
        "All Files"
      )
    )
  );

export default Sidebar;
