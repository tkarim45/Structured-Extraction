import React, { useState } from "react";
import axios from "axios";

const FileUpload = () => {
  const [file, setFile] = useState(null);
  const [message, setMessage] = useState("");

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setMessage(""); // Clear previous message
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!file) {
      setMessage("Please select a file");
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    axios
      .post("http://localhost:8000/upload", formData)
      .then((response) => setMessage(response.data.message))
      .catch((error) => {
        const errorMsg = error.response?.data?.detail || "Error uploading file";
        setMessage(errorMsg);
      });
  };

  return React.createElement(
    "div",
    { className: "max-w-md mx-auto" },
    React.createElement("h2", { className: "text-3xl font-bold mb-6" }, "Upload File"),
    React.createElement(
      "form",
      { onSubmit: handleSubmit },
      React.createElement("input", {
        type: "file",
        onChange: handleFileChange,
        className: "p-2 border rounded-lg w-full mb-4",
        accept: ".csv,.xlsx",
      }),
      React.createElement("button", { type: "submit", className: "bg-primary text-white p-2 rounded-lg w-full" }, "Upload")
    ),
    message && React.createElement("p", { className: `mt-4 ${message.includes("Error") ? "text-red-500" : "text-accent"}` }, message)
  );
};

export default FileUpload;
