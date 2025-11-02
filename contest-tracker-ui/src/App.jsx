import React, { useState } from 'react';
import { Loader, Check, AlertTriangle, Play } from 'lucide-react';

export default function App() {
  // States: 'idle', 'syncing', 'synced', 'error'
  const [syncState, setSyncState] = useState('idle');
  const [syncStats, setSyncStats] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');

  const handleSync = async () => {
    setSyncState('syncing');
    setSyncStats(null);
    setErrorMessage('');

    try {
      // Assumes the Flask backend is running on http://127.0.0.1:5000
      const response = await fetch('http://127.0.0.1:5000/');

      if (!response.ok) {
        let errorMsg = `HTTP error! status: ${response.status}`;
        try {
          const errData = await response.json();
          errorMsg = errData.error || errorMsg;
        } catch (e) {
          // Response was not JSON
        }
        throw new Error(errorMsg);
      }

      const data = await response.json();
      setSyncStats(data);
      setSyncState('synced');

    } catch (error) {
      console.error("Sync failed:", error);
      setErrorMessage(error.message || 'Failed to connect to the backend. Is it running?');
      setSyncState('error');
    }
  };

  const RenderState = () => {
    switch (syncState) {
      case 'syncing':
        return (
          <>
            <Loader className="w-16 h-16 text-blue-400 animate-spin" />
            <h2 className="mt-4 text-2xl font-semibold text-white">
              Syncing Contests
            </h2>
            <p className="text-gray-400">Please wait, fetching from all platforms...</p>
          </>
        );
      case 'synced':
        return (
          <>
            <Check className="w-16 h-16 text-green-400" />
            <h2 className="mt-4 text-2xl font-semibold text-white">
              Sync Complete
            </h2>
            <div className="mt-2 text-center text-gray-300">
              <p>New Contests Added: <span className="font-bold text-white">{syncStats?.new_contests_added}</span></p>
              <p>Total Contests Checked: <span className="font-bold text-white">{syncStats?.total_contests_checked}</span></p>
            </div>
            <button
              onClick={handleSync}
              className="mt-6 px-6 py-2 bg-blue-600 text-white font-semibold rounded-full shadow-lg hover:bg-blue-700 transition duration-300 ease-in-out flex items-center justify-center space-x-2"
            >
              <Play className="w-5 h-5" />
              <span>Run Sync Again</span>
            </button>
          </>
        );
      case 'error':
        return (
          <>
            <AlertTriangle className="w-16 h-16 text-red-400" />
            <h2 className="mt-4 text-2xl font-semibold text-white">
              Sync Failed
            </h2>
            <p className="mt-2 text-center text-red-300 max-w-xs">
              {errorMessage}
            </p>
            <button
              onClick={handleSync}
              className="mt-6 px-6 py-2 bg-blue-600 text-white font-semibold rounded-full shadow-lg hover:bg-blue-700 transition duration-300 ease-in-out flex items-center justify-center space-x-2"
            >
              <Play className="w-5 h-5" />
              <span>Try Again</span>
            </button>
          </>
        );
      case 'idle':
      default:
        return (
          <>
            <h1 className="text-3xl font-bold text-white">
              Contest Tracker
            </h1>
            <p className="mt-2 text-gray-300">
              Sync coding contests to your Google Tasks.
            </p>
            <button
              onClick={handleSync}
              className="mt-8 px-8 py-3 bg-gradient-to-r from-blue-500 to-purple-600 text-white font-bold rounded-full shadow-2xl hover:scale-105 transform transition duration-300 ease-in-out flex items-center justify-center space-x-2"
            >
              <Play className="w-6 h-6" />
              <span>Begin Sync</span>
            </button>
          </>
        );
    }
  };

  return (
    <div className="min-h-screen w-full bg-gray-900 text-white font-sans flex items-center justify-center p-4">
      {/* Background Gradient Elements */}
      <div className="absolute top-0 left-0 w-64 h-64 bg-purple-600 rounded-full filter blur-3xl opacity-30 animate-blob"></div>
      <div className="absolute top-0 right-0 w-72 h-72 bg-blue-600 rounded-full filter blur-3xl opacity-30 animate-blob animation-delay-2000"></div>
      <div className="absolute bottom-0 left-1/4 w-64 h-64 bg-pink-600 rounded-full filter blur-3xl opacity-30 animate-blob animation-delay-4000"></div>
      
      {/* Main Card */}
      <div className="relative z-10 w-full max-w-md h-96 bg-black bg-opacity-30 backdrop-filter backdrop-blur-xl rounded-2xl shadow-2xl border border-gray-700 overflow-hidden">
        <div className="w-full h-full flex flex-col items-center justify-center text-center p-8">
          <RenderState />
        </div>
      </div>
      
      {/* Add custom animation styles for the blobs */}
      <style>
        {`
          @keyframes blob {
            0% { transform: translate(0px, 0px) scale(1); }
            33% { transform: translate(30px, -50px) scale(1.1); }
            66% { transform: translate(-20px, 20px) scale(0.9); }
            100% { transform: translate(0px, 0px) scale(1); }
          }
          .animate-blob {
            animation: blob 7s infinite;
          }
          .animation-delay-2000 {
            animation-delay: 2s;
          }
          .animation-delay-4000 {
            animation-delay: 4s;
          }
        `}
      </style>
    </div>
  );
}
