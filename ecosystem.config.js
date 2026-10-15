module.exports = {
  apps: [
    {
      name: "citeguard",
      script: "/home/hoi/Citation-Verifier/.venv/bin/gunicorn",
      args: "--bind 172.18.0.1:5000 --workers 2 --timeout 180 --graceful-timeout 30 webapp:app",
      cwd: "/home/hoi/Citation-Verifier",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
      },
      max_memory_restart: "500M",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
    },
  ],
};
