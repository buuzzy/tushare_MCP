module.exports = {
  apps: [
    {
      name: "tushare-mcp-stock",
      script: ".\\venv\\Scripts\\python.exe",
      args: "server.py --category stock --port 8000",
      cwd: "c:\\project\\tushare_MCP",
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      env: {
        NODE_ENV: "production"
      }
    },
    {
      name: "tushare-mcp-fund",
      script: ".\\venv\\Scripts\\python.exe",
      args: "server.py --category fund --port 8001",
      cwd: "c:\\project\\tushare_MCP",
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      env: {
        NODE_ENV: "production"
      }
    }
  ]
};
