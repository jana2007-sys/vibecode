import { Route, Routes } from "react-router-dom";
import { MainLayout } from "./layouts/MainLayout";
import { Landing } from "./pages/Landing";
import { CandidateSelection } from "./pages/CandidateSelection";
import { Interview } from "./pages/Interview";
import { Report } from "./pages/Report";
import { NotFound } from "./pages/NotFound";

export default function App() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/" element={<Landing />} />
        <Route path="/candidates" element={<CandidateSelection />} />
        <Route path="/interview" element={<Interview />} />
        <Route path="/report" element={<Report />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
