/**
 * RuggyLab Malaria Dataset Collector
 * Système de collecte et d'annotation d'images pour l'entraînement IA paludisme
 */

class MalariaDatasetCollector {
  constructor(dataManager) {
    this.dataManager = dataManager;
    this.currentDataset = null;
    this.annotationMode = 'simple'; // 'simple', 'detailed', 'bounding_box'
    this.qualityThreshold = 0.7;
  }

  /**
   * Initialiser le dataset de paludisme
   */
  initializeMalariaDataset() {
    const existingDatasets = this.dataManager.getDatasetsByType('malaria');
    
    if (existingDatasets.length > 0) {
      this.currentDataset = existingDatasets[0];
      console.log('Dataset paludisme existant chargé:', this.currentDataset.name);
      return this.currentDataset;
    }

    // Créer un nouveau dataset
    this.currentDataset = this.dataManager.createDataset(
      'malaria_detection_v1',
      'malaria',
      'Dataset pour détection de parasites Plasmodium dans les frottis sanguins'
    );

    console.log('Nouveau dataset paludisme créé:', this.currentDataset.name);
    return this.currentDataset;
  }

  /**
   * Collecter une image depuis le microscope
   */
  async collectMicroscopeImage(imageData, initialLabel = null) {
    if (!this.currentDataset) {
      this.initializeMalariaDataset();
    }

    // Analyser la qualité de l'image
    const quality = await this.assessImageQuality(imageData);
    
    if (quality.score < this.qualityThreshold) {
      console.warn('Qualité image insuffisante:', quality.score);
      return {
        success: false,
        reason: 'low_quality',
        quality: quality
      };
    }

    // Déterminer le label initial si non fourni
    const label = initialLabel || await this.autoLabelImage(imageData);

    // Ajouter l'échantillon au dataset
    const sample = this.dataManager.addSample(
      this.currentDataset.id,
      imageData,
      label,
      {
        source: 'microscope',
        quality: quality.score,
        qualityDetails: quality,
        collector: 'automated'
      }
    );

    return {
      success: true,
      sample: sample,
      quality: quality,
      label: label
    };
  }

  /**
   * Évaluer la qualité d'une image
   */
  async assessImageQuality(imageData) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = img.width;
        canvas.height = img.height;
        ctx.drawImage(img, 0, 0);

        // Analyser la qualité
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const quality = this.calculateImageQuality(imageData);
        
        resolve(quality);
      };
      
      img.onerror = () => {
        resolve({ score: 0, issues: ['image_load_error'] });
      };
      
      img.src = imageData;
    });
  }

  /**
   * Calculer les métriques de qualité d'image
   */
  calculateImageQuality(imageData) {
    const data = imageData.data;
    const issues = [];
    let score = 1.0;

    // Vérifier la luminosité
    let totalBrightness = 0;
    for (let i = 0; i < data.length; i += 4) {
      const brightness = (data[i] + data[i + 1] + data[i + 2]) / 3;
      totalBrightness += brightness;
    }
    const avgBrightness = totalBrightness / (data.length / 4);

    if (avgBrightness < 50) {
      issues.push('too_dark');
      score -= 0.3;
    } else if (avgBrightness > 200) {
      issues.push('too_bright');
      score -= 0.2;
    }

    // Vérifier le contraste
    let minBrightness = 255;
    let maxBrightness = 0;
    for (let i = 0; i < data.length; i += 4) {
      const brightness = (data[i] + data[i + 1] + data[i + 2]) / 3;
      minBrightness = Math.min(minBrightness, brightness);
      maxBrightness = Math.max(maxBrightness, brightness);
    }
    const contrast = maxBrightness - minBrightness;

    if (contrast < 50) {
      issues.push('low_contrast');
      score -= 0.2;
    }

    // Vérifier le bruit (simplifié)
    let noise = 0;
    for (let i = 0; i < Math.min(data.length, 10000); i += 4) {
      const brightness = (data[i] + data[i + 1] + data[i + 2]) / 3;
      const nextBrightness = (data[i + 4] + data[i + 5] + data[i + 6]) / 3;
      noise += Math.abs(brightness - nextBrightness);
    }
    const avgNoise = noise / (Math.min(data.length, 10000) / 4);

    if (avgNoise > 30) {
      issues.push('high_noise');
      score -= 0.15;
    }

    return {
      score: Math.max(0, score),
      brightness: avgBrightness,
      contrast: contrast,
      noise: avgNoise,
      issues: issues
    };
  }

  /**
   * Annotation automatique initiale (placeholder)
   */
  async autoLabelImage(imageData) {
    // Pour l'instant, retourne 'unlabeled' - sera remplacé par IA
    return 'unlabeled';
  }

  /**
   * Annoter manuellement un échantillon
   */
  annotateSample(sampleId, annotation) {
    const annotationData = {
      ...annotation,
      annotatedBy: 'human',
      timestamp: new Date().toISOString(),
      confidence: 1.0
    };

    return this.dataManager.addAnnotation(sampleId, annotationData);
  }

  /**
   * Annotation détaillée avec bounding boxes
   */
  annotateWithBoundingBoxes(sampleId, boxes) {
    const annotation = {
      type: 'bounding_box',
      boxes: boxes.map(box => ({
        x: box.x,
        y: box.y,
        width: box.width,
        height: box.height,
        label: box.label, // 'parasite', 'cell', 'artifact'
        confidence: box.confidence || 1.0
      })),
      totalParasites: boxes.filter(b => b.label === 'parasite').length
    };

    return this.annotateSample(sampleId, annotation);
  }

  /**
   * Annotation simple (positif/négatif)
   */
  annotateSimple(sampleId, isPositive, confidence = 1.0) {
    const annotation = {
      type: 'simple',
      label: isPositive ? 'positive' : 'negative',
      confidence: confidence,
      notes: ''
    };

    return this.annotateSample(sampleId, annotation);
  }

  /**
   * Annotation détaillée avec compte de parasites
   */
  annotateDetailed(sampleId, parasiteCount, cellCount, notes = '') {
    const annotation = {
      type: 'detailed',
      parasiteCount: parasiteCount,
      cellCount: cellCount,
      parasitemia: (parasiteCount / cellCount * 100).toFixed(2),
      notes: notes,
      confidence: 1.0
    };

    return this.annotateSample(sampleId, annotation);
  }

  /**
   * Obtenir les statistiques du dataset
   */
  getDatasetStatistics() {
    if (!this.currentDataset) {
      return null;
    }

    const stats = this.dataManager.getDatasetStats(this.currentDataset.id);
    
    // Statistiques spécifiques paludisme
    const labelStats = {
      positive: 0,
      negative: 0,
      unlabeled: 0
    };

    this.currentDataset.samples.forEach(sample => {
      if (labelStats[sample.label] !== undefined) {
        labelStats[sample.label]++;
      } else {
        labelStats.unlabeled++;
      }
    });

    return {
      ...stats,
      malariaSpecific: labelStats,
      annotationRate: (this.currentDataset.samples.length - labelStats.unlabeled) / 
                       this.currentDataset.samples.length * 100
    };
  }

  /**
   * Préparer les données pour l'entraînement
   */
  prepareForTraining(testSplit = 0.2) {
    if (!this.currentDataset) {
      throw new Error('Aucun dataset initialisé');
    }

    // Filtrer uniquement les échantillons annotés
    const annotatedSamples = this.currentDataset.samples.filter(
      sample => sample.label !== 'unlabeled'
    );

    if (annotatedSamples.length < 10) {
      throw new Error("Pas assez d'échantillons annotés pour l'entraînement");
    }

    const trainingData = this.dataManager.prepareTrainingData(
      this.currentDataset.id,
      testSplit
    );

    return {
      ...trainingData,
      annotatedSamples: annotatedSamples.length,
      readyForTraining: annotatedSamples.length >= 50
    };
  }

  /**
   * Exporter le dataset pour l'entraînement
   */
  exportForTraining() {
    if (!this.currentDataset) {
      throw new Error('Aucun dataset initialisé');
    }

    const trainingData = this.prepareForTraining();
    const exportData = {
      dataset: this.currentDataset,
      trainingData: trainingData,
      exported: new Date().toISOString(),
      format: 'tensorflow_js'
    };

    return JSON.stringify(exportData, null, 2);
  }

  /**
   * Importer des images depuis un dossier (simulation)
   */
  async importFromFolder(folderPath, label = null) {
    // Cette fonction serait utilisée avec File System Access API
    // Pour l'instant, c'est un placeholder
    
    console.log('Import depuis dossier:', folderPath);
    return {
      success: false,
      reason: 'requires_file_system_api'
    };
  }

  /**
   * Valider les annotations
   */
  validateAnnotations() {
    if (!this.currentDataset) {
      return { valid: false, issues: ['no_dataset'] };
    }

    const issues = [];
    
    this.currentDataset.samples.forEach(sample => {
      const sampleAnnotations = Array.from(this.dataManager.annotations.values())
        .filter(ann => ann.sampleId === sample.id);

      if (sampleAnnotations.length === 0) {
        issues.push(`Sample ${sample.id} non annoté`);
      }

      if (sampleAnnotations.length > 1) {
        issues.push(`Sample ${sample.id} a plusieurs annotations`);
      }
    });

    return {
      valid: issues.length === 0,
      issues: issues,
      totalSamples: this.currentDataset.samples.length,
      annotatedSamples: this.currentDataset.samples.length - 
                        issues.filter(i => i.includes('non annoté')).length
    };
  }

  /**
   * Nettoyer le dataset (supprimer les échantillons de mauvaise qualité)
   */
  cleanupDataset(minQuality = 0.6) {
    if (!this.currentDataset) {
      throw new Error('Aucun dataset initialisé');
    }

    const originalSize = this.currentDataset.samples.length;
    this.currentDataset.samples = this.currentDataset.samples.filter(
      sample => sample.metadata.quality >= minQuality
    );

    const removedCount = originalSize - this.currentDataset.samples.length;
    this.currentDataset.size = this.currentDataset.samples.length;
    this.dataManager.datasets.set(this.currentDataset.id, this.currentDataset);
    this.dataManager.saveToStorage();

    return {
      originalSize: originalSize,
      newSize: this.currentDataset.samples.length,
      removedCount: removedCount
    };
  }
}

// Instance globale du collecteur de dataset paludisme
const malariaDatasetCollector = new MalariaDatasetCollector(trainingDataManager);
