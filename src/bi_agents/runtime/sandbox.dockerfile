FROM python:3.12.4-slim-bullseye

WORKDIR /workspace

RUN pip install --no-cache-dir \
    antiorm==1.2.1 \
    contourpy==1.3.2 \
    cycler==0.12.1 \
    db==0.1.1 \
    db-sqlite3==0.0.1 \
    fonttools==4.59.0 \
    joblib==1.5.1 \
    kiwisolver==1.4.8 \
    matplotlib==3.10.3 \
    mysql-connector-python==9.3.0 \
    numpy==2.3.1 \
    packaging==25.0 \
    pandas==2.3.1 \
    patsy==1.0.1 \
    pillow==11.3.0 \
    pyparsing==3.2.3 \
    python-dateutil==2.9.0.post0 \
    pytz==2025.2 \
    scikit-learn==1.7.1 \
    scipy==1.16.0 \
    seaborn==0.13.2 \
    six==1.17.0 \
    statsmodels==0.14.5 \
    threadpoolctl==3.6.0 \
    tzdata==2025.2

CMD ["tail", "-f", "/dev/null"]