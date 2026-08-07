/** Shared page shell: Navbar + content outlet + Footer. */

import { Outlet } from "react-router-dom";
import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { InterviewProvider } from "../context/InterviewContext";

export function MainLayout() {
  return (
    <InterviewProvider>
      <div className="flex min-h-full flex-col">
        <Navbar />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
          <Outlet />
        </main>
        <Footer />
      </div>
    </InterviewProvider>
  );
}
