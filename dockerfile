FROM python:3.11

# Prevent Python from writing pyc files and buffer output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy only requirements first (for better caching)
COPY requirements.txt .

# Install dependencies (cached unless requirements.txt changes)
RUN pip install -r requirements.txt

# Now copy the rest of the project
COPY . .

# Collect static files safely (won’t fail if STATIC_ROOT not set)
#RUN DJANGO_SETTINGS_MODULE=projectname.settings \
#    python main.py collectstatic --noinput || true

# Expose the custom port
EXPOSE 7207

# Start the pyhon app
CMD ["uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "7207"]
