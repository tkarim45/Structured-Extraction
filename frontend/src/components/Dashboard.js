import React, { useState, useEffect } from "react";
import axios from "axios";
import Filters from "./Filters";
import Table from "./Table";

const Dashboard = () => {
  const [files, setFiles] = useState([]);
  const [filters, setFilters] = useState({ sort: "", status: "", action: "" });

  useEffect(() => {
    axios
      .get("http://localhost:8000/files", { params: filters })
      .then((response) => setFiles(response.data))
      .catch((error) => console.error("Error fetching files:", error));
  }, [filters]);

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  return React.createElement("div", null, React.createElement("h2", { className: "text-3xl font-bold mb-6" }, "Dashboard"), React.createElement(Filters, { onFilterChange: handleFilterChange }), React.createElement(Table, { data: files }));
};

export default Dashboard;
