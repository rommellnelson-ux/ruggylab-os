-- 1. Table des Equipements
CREATE TABLE IF NOT EXISTS equipments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    serial_number VARCHAR(100) UNIQUE,
    type VARCHAR(50),
    location VARCHAR(100),
    last_calibration DATE
);

-- 2. Table des Patients
CREATE TABLE IF NOT EXISTS patients (
    id SERIAL PRIMARY KEY,
    ipp_unique_id VARCHAR(50) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    birth_date DATE NOT NULL,
    sex CHAR(1) CHECK (sex IN ('M', 'F', 'U')),
    rank VARCHAR(50)
);

-- 3. Table des Echantillons
CREATE TABLE IF NOT EXISTS samples (
    id SERIAL PRIMARY KEY,
    barcode VARCHAR(100) UNIQUE NOT NULL,
    patient_id INTEGER REFERENCES patients(id),
    collection_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    received_date TIMESTAMP,
    status VARCHAR(50)
);

-- 4. Table des Resultats
CREATE TABLE IF NOT EXISTS results (
    id SERIAL PRIMARY KEY,
    sample_id INTEGER REFERENCES samples(id) NOT NULL,
    equipment_id INTEGER REFERENCES equipments(id),
    analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_points JSONB NOT NULL,
    image_url VARCHAR(255),
    validator_id INTEGER,
    is_validated BOOLEAN DEFAULT FALSE,
    is_critical BOOLEAN DEFAULT FALSE
);
