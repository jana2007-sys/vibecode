/** Shared page shell: Navbar + content outlet + Footer. */

import { Outlet, useLocation } from "react-router-dom";
import { Footer } from "../components/Footer";
import { Navbar } from "../components/Navbar";
import { InterviewProvider } from "../context/InterviewContext";

export function MainLayout() {
  const location = useLocation();
  const isInterview = location.pathname === "/interview";

  return (
    <InterviewProvider>
      <div className="flex min-h-screen flex-col">
        <Navbar />
        <main
          className={
            isInterview
              ? "flex w-full flex-1 flex-col"
              : "mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 sm:py-10 lg:px-8"
          }
        >
          <Outlet />
        </main>
        {!isInterview ? <Footer /> : null}
      </div>
    </InterviewProvider>
  );
}
