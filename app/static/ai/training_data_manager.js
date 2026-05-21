/**
 * RuggyLab AI Training Data Manager
 * Gestion des données d'entraînement pour les modèles IA
 */

class TrainingDataManager {
  constructor() {
    this.datasets = new Map();
    this.annotations = new Map();
    this.metadata = new Map();
    this.storageKey = 'ruggylab_ai_training_data';
    
    this.initializeStorage();
  }

  /**
   * Initialiser le stockage local pour les données d'entraînement
   */
  initializeStorage() {
    try {
      const storedData = localStorage.getItem(this.storageKey);
      if (storedData) {
        const data = JSON.parse(storedData);
        this.datasets = new Map(data.datasets || []);
        this.annotations = new Map(data.annotations || []);
        this.metadata = new Map(data.metadata || []);
      }
    } catch (error) {
      console.error('Erreur initialisation stockage:', error);
    }
  }

  /**
   * Sauvegarder les données dans le stockage local
   */
  saveToStorage() {
    try {
      const data = {
        datasets: Array.from(this.datasets.entries()),
        annotations: Array.from(this.annotations.entries()),
        metadata: Array.from(this.metadata.entries())
      };
      localStorage.setItem(this.storageKey, JSON.stringify(data));
    } catch (error) {
      console.error('Erreur sauvegarde stockage:', error);
    }
  }

  /**
   * Créer un nouveau dataset d'entraînement
   */
  createDataset(name, type, description = '') {
    const dataset = {
      id: this.generateId(),
      name: name,
      type: type, // 'malaria', 'anomaly', 'general'
      description: description,
      created: new Date().toISOString(),
      samples: [],
      size: 0,
      status: 'active'
    };
    
    this.datasets.set(dataset.id, dataset);
    this.saveToStorage();
    
    return dataset;
  }

  /**
   * Ajouter un échantillon au dataset
   */
  addSample(datasetId, imageData, label, metadata = {}) {
    const dataset = this.datasets.get(datasetId);
    if (!dataset) {
      throw new Error('Dataset non trouvé');
    }

    const sample = {
      id: this.generateId(),
      imageData: imageData, // Base64 ou URL
      label: label, // 'positive', 'negative', etc.
      metadata: {
        added: new Date().toISOString(),
        source: metadata.source || 'manual',
        quality: metadata.quality || 'unknown',
        ...metadata
      }
    };

    dataset.samples.push(sample);
    dataset.size = dataset.samples.length;
    
    this.datasets.set(datasetId, dataset);
    this.saveToStorage();
    
    return sample;
  }

  /**
   * Ajouter une annotation à un échantillon
   */
  addAnnotation(sampleId, annotationData) {
    const annotation = {
      id: this.generateId(),
      sampleId: sampleId,
      data: annotationData,
      created: new Date().toISOString(),
      verified: false
    };
    
    this.annotations.set(annotation.id, annotation);
    this.saveToStorage();
    
    return annotation;
  }

  /**
   * Récupérer un dataset par ID
   */
  getDataset(datasetId) {
    return this.datasets.get(datasetId);
  }

  /**
   * Récupérer tous les datasets d'un type
   */
  getDatasetsByType(type) {
    return Array.from(this.datasets.values()).filter(ds => ds.type === type);
  }

  /**
   * Préparer les données pour l'entraînement TensorFlow.js
   */
  prepareTrainingData(datasetId, testSplit = 0.2) {
    const dataset = this.datasets.get(datasetId);
    if (!dataset) {
      throw new Error('Dataset non trouvé');
    }

    const samples = dataset.samples;
    const shuffled = this.shuffleArray([...samples]);
    
    const splitIndex = Math.floor(shuffled.length * (1 - testSplit));
    
    return {
      training: shuffled.slice(0, splitIndex),
      testing: shuffled.slice(splitIndex),
      total: shuffled.length,
      trainingSize: splitIndex,
      testingSize: shuffled.length - splitIndex
    };
  }

  /**
   * Convertir les données en format TensorFlow.js
   */
  convertToTensorFormat(data, imageSize = 224) {
    const images = [];
    const labels = [];
    
    data.forEach(sample => {
      // Convertir l'image en tensor
      const imageTensor = this.imageToTensor(sample.imageData, imageSize);
      images.push(imageTensor);
      
      // Convertir le label en one-hot encoding
      const labelTensor = this.labelToTensor(sample.label);
      labels.push(labelTensor);
    });
    
    return {
      images: tf.stack(images),
      labels: tf.stack(labels)
    };
  }

  /**
   * Convertir une image en tensor
   */
  imageToTensor(imageData, size) {
    return tf.tidy(() => {
      // Créer un tensor à partir de l'image
      return tf.browser.fromPixels(imageData)
        .resizeNearestNeighbor([size, size])
        .toFloat()
        .div(255.0)
        .expandDims(0);
    });
  }

  /**
   * Convertir un label en tensor one-hot
   */
  labelToTensor(label) {
    const labelMap = {
      'positive': [1, 0],
      'negative': [0, 1],
      'parasitized': [1, 0],
      'uninfected': [0, 1]
    };
    
    return tf.tensor1d(labelMap[label] || [0, 1]);
  }

  /**
   * Mélanger un tableau (Fisher-Yates shuffle)
   */
  shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
  }

  /**
   * Générer un ID unique
   */
  generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substr(2);
  }

  /**
   * Obtenir des statistiques sur le dataset
   */
  getDatasetStats(datasetId) {
    const dataset = this.datasets.get(datasetId);
    if (!dataset) {
      return null;
    }

    const labelCounts = {};
    dataset.samples.forEach(sample => {
      labelCounts[sample.label] = (labelCounts[sample.label] || 0) + 1;
    });

    return {
      totalSamples: dataset.samples.length,
      labelDistribution: labelCounts,
      created: dataset.created,
      lastUpdated: new Date().toISOString()
    };
  }

  /**
   * Exporter un dataset en JSON
   */
  exportDataset(datasetId) {
    const dataset = this.datasets.get(datasetId);
    if (!dataset) {
      throw new Error('Dataset non trouvé');
    }

    const exportData = {
      dataset: dataset,
      annotations: Array.from(this.annotations.values())
        .filter(ann => dataset.samples.some(s => s.id === ann.sampleId)),
      exported: new Date().toISOString()
    };

    return JSON.stringify(exportData, null, 2);
  }

  /**
   * Importer un dataset depuis JSON
   */
  importDataset(jsonData) {
    try {
      const data = JSON.parse(jsonData);
      
      // Importer le dataset
      this.datasets.set(data.dataset.id, data.dataset);
      
      // Importer les annotations
      data.annotations.forEach(ann => {
        this.annotations.set(ann.id, ann);
      });
      
      this.saveToStorage();
      
      return data.dataset;
    } catch (error) {
      throw new Error('Erreur import dataset: ' + error.message);
    }
  }

  /**
   * Supprimer un dataset
   */
  deleteDataset(datasetId) {
    const dataset = this.datasets.get(datasetId);
    if (!dataset) {
      throw new Error('Dataset non trouvé');
    }

    // Supprimer les annotations associées
    dataset.samples.forEach(sample => {
      const relatedAnnotations = Array.from(this.annotations.values())
        .filter(ann => ann.sampleId === sample.id);
      
      relatedAnnotations.forEach(ann => {
        this.annotations.delete(ann.id);
      });
    });

    this.datasets.delete(datasetId);
    this.saveToStorage();
  }
}

// Instance globale du gestionnaire de données d'entraînement
const trainingDataManager = new TrainingDataManager();
