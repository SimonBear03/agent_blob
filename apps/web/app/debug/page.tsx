'use client'

export default function DebugPage() {
  // Check what API URL is actually being used
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'NOT SET'
  
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">Debug Info</h1>
      
      <div className="space-y-4">
        <div className="p-4 bg-gray-100 rounded">
          <strong>NEXT_PUBLIC_API_URL:</strong>
          <pre className="mt-2">{apiUrl}</pre>
        </div>
        
        <div className="p-4 bg-gray-100 rounded">
          <strong>Window Location:</strong>
          <pre className="mt-2">{typeof window !== 'undefined' ? window.location.href : 'Server side'}</pre>
        </div>
        
        <div className="p-4 bg-gray-100 rounded">
          <strong>All NEXT_PUBLIC_* vars:</strong>
          <pre className="mt-2">
            {JSON.stringify(
              Object.keys(process.env)
                .filter(key => key.startsWith('NEXT_PUBLIC_'))
                .reduce((obj, key) => ({ ...obj, [key]: process.env[key] }), {}),
              null,
              2
            )}
          </pre>
        </div>
      </div>
    </div>
  )
}
