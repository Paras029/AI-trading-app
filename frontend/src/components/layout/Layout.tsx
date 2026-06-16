import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { useStore } from "../../store";
import clsx from "clsx";

export function Layout() {
  const { notification, setNotification } = useStore();

  return (
    <div className="flex min-h-screen bg-cream font-sans">
      <Sidebar />
      <main className="flex-1 flex flex-col">
        {notification && (
          <div className="bg-amber-50 border-b border-amber-200 px-6 py-2 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-amber-800">
              <span className="text-base">🎯</span>
              {notification}
            </div>
            <button
              onClick={() => setNotification(null)}
              className="text-amber-500 hover:text-amber-700 text-lg leading-none"
            >
              ×
            </button>
          </div>
        )}
        <div className="flex-1 p-6 overflow-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
