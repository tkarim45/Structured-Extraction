import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Home from "./pages/Home";
import Upload from "./pages/Upload";
import FileDetails from "./pages/FileDetails";

const App = () =>
  React.createElement(
    BrowserRouter,
    null,
    React.createElement("div", { className: "flex" }, React.createElement(Sidebar), React.createElement("div", { className: "flex-1 p-6 bg-secondary min-h-screen" }, React.createElement(Routes, null, React.createElement(Route, { path: "/", element: React.createElement(Home) }), React.createElement(Route, { path: "/upload", element: React.createElement(Upload) }), React.createElement(Route, { path: "/file/:id", element: React.createElement(FileDetails) }))))
  );

export default App;
