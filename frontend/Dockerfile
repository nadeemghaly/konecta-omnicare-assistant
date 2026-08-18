FROM python:3.12-slim

WORKDIR /srv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY frontend/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY frontend/app.py frontend/theme.py /srv/
COPY frontend/.streamlit /srv/.streamlit

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health',timeout=4).status==200 else 1)"

# headless stops Streamlit trying to open a browser inside the container;
# the CORS/XSRF flags keep it reachable from the host without a warning banner.
CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
