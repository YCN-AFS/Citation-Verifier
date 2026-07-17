module.exports = {
  apps: [
    {
      name: "citeguard",
      script: "/home/hoi/Citation-Verifier/.venv/bin/gunicorn",
      args: "--bind 0.0.0.0:5000 --workers 2 --timeout 120 webapp:app",
      cwd: "/home/hoi/Citation-Verifier",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
      },
      max_memory_restart: "200M",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
    },
  ],
};
