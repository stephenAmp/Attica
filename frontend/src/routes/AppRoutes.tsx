import { Routes, Route } from "react-router-dom";
import ReleasesPage from "../pages/releasePage";
import { Endpoints } from "../constants/endpoints";

export default function AppRoutes() {

  return (
    <Routes>
      <Route
        path={Endpoints.releases.urlPath}
        element={<ReleasesPage />}
      />

      <Route path="/" element={<h1>Welcome to Attica Community</h1>} />

      <Route path="*" element={<h1>Page not found</h1>} />
    </Routes>
  );
}