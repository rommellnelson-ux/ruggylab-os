/**
 * RuggyLab AI Model Validator
 * Système de validation et de testing des modèles IA
 */

class ModelValidator {
  constructor() {
    this.validationResults = new Map();
    this.benchmarkResults = new Map();
    this.performanceMetrics = new Map();
    this.storageKey = 'ruggylab_ai_validation_results';
    
    this.initializeStorage();
  }

  /**
   * Initialiser le stockage local pour les résultats de validation
   */
  initializeStorage() {
    try {
      const storedData = localStorage.getItem(this.storageKey);
      if (storedData) {
        const data = JSON.parse(storedData);
        this.validationResults = new Map(data.validationResults || []);
        this.benchmarkResults = new Map(data.benchmarkResults || []);
        this.performanceMetrics = new Map(data.performanceMetrics || []);
      }
    } catch (error) {
      console.error('Erreur initialisation stockage validation:', error);
    }
  }

  /**
   * Sauvegarder les résultats dans le stockage local
   */
  saveToStorage() {
    try {
      const data = {
        validationResults: Array.from(this.validationResults.entries()),
        benchmarkResults: Array.from(this.benchmarkResults.entries()),
        performanceMetrics: Array.from(this.performanceMetrics.entries())
      };
      localStorage.setItem(this.storageKey, JSON.stringify(data));
    } catch (error) {
      console.error('Erreur sauvegarde validation:', error);
    }
  }

  /**
   * Valider un modèle de détection de paludisme
   */
  async validateMalariaModel(model, testData) {
    const validationId = this.generateId();
    const results = {
      id: validationId,
      modelType: 'malaria_detection',
      timestamp: new Date().toISOString(),
      testSize: testData.length,
      predictions: [],
      metrics: {}
    };

    let correctPredictions = 0;
    let truePositives = 0;
    let trueNegatives = 0;
    let falsePositives = 0;
    let falseNegatives = 0;

    for (const sample of testData) {
      try {
        // Simuler la prédiction du modèle
        const prediction = await this.predictMalaria(model, sample.imageData);
        
        const actualLabel = sample.label;
        const predictedLabel = prediction.label;
        const confidence = prediction.confidence;

        results.predictions.push({
          sampleId: sample.id,
          actual: actualLabel,
          predicted: predictedLabel,
          confidence: confidence,
          correct: actualLabel === predictedLabel
        });

        if (actualLabel === predictedLabel) {
          correctPredictions++;
          if (actualLabel === 'positive') {
            truePositives++;
          } else {
            trueNegatives++;
          }
        } else {
          if (actualLabel === 'positive' && predictedLabel === 'negative') {
            falseNegatives++;
          } else if (actualLabel === 'negative' && predictedLabel === 'positive') {
            falsePositives++;
          }
        }
      } catch (error) {
        console.error('Erreur prédiction:', error);
      }
    }

    // Calculer les métriques
    results.metrics = this.calculateMetrics({
      correctPredictions,
      truePositives,
      trueNegatives,
      falsePositives,
      falseNegatives,
      totalSamples: testData.length
    });

    this.validationResults.set(validationId, results);
    this.saveToStorage();

    return results;
  }

  /**
   * Simuler la prédiction de paludisme (placeholder)
   */
  async predictMalaria(model, imageData) {
    // Pour l'instant, simuler une prédiction
    // Dans la réalité, ceci utiliserait le modèle TensorFlow.js
    const random = Math.random();
    return {
      label: random > 0.5 ? 'positive' : 'negative',
      confidence: random
    };
  }

  /**
   * Calculer les métriques de performance
   */
  calculateMetrics(metrics) {
    const { correctPredictions, truePositives, trueNegatives, falsePositives, falseNegatives, totalSamples } = metrics;

    const accuracy = totalSamples > 0 ? (correctPredictions / totalSamples) * 100 : 0;
    const precision = (truePositives + falsePositives) > 0 ? (truePositives / (truePositives + falsePositives)) * 100 : 0;
    const recall = (truePositives + falseNegatives) > 0 ? (truePositives / (truePositives + falseNegatives)) * 100 : 0;
    const specificity = (trueNegatives + falsePositives) > 0 ? (trueNegatives / (trueNegatives + falsePositives)) * 100 : 0;
    const f1Score = (precision + recall) > 0 ? 2 * ((precision * recall) / (precision + recall)) : 0;

    return {
      accuracy: accuracy.toFixed(2),
      precision: precision.toFixed(2),
      recall: recall.toFixed(2),
      specificity: specificity.toFixed(2),
      f1Score: f1Score.toFixed(2),
      truePositives,
      trueNegatives,
      falsePositives,
      falseNegatives,
      correctPredictions,
      totalSamples
    };
  }

  /**
   * Valider le modèle de détection d'anomalies
   */
  async validateAnomalyModel(model, testData) {
    const validationId = this.generateId();
    const results = {
      id: validationId,
      modelType: 'anomaly_detection',
      timestamp: new Date().toISOString(),
      testSize: testData.length,
      predictions: [],
      metrics: {}
    };

    let correctPredictions = 0;
    let detectedAnomalies = 0;
    let actualAnomalies = 0;
    let missedAnomalies = 0;
    let falseAlarms = 0;

    for (const sample of testData) {
      try {
        const prediction = await this.predictAnomaly(model, sample);
        
        const hasAnomaly = sample.hasAnomaly || false;
        const detectedAnomaly = prediction.hasAnomaly;

        results.predictions.push({
          sampleId: sample.id,
          hasAnomaly: hasAnomaly,
          detectedAnomaly: detectedAnomaly,
          confidence: prediction.confidence,
          correct: hasAnomaly === detectedAnomaly
        });

        if (hasAnomaly === detectedAnomaly) {
          correctPredictions++;
        }

        if (hasAnomaly) {
          actualAnomalies++;
          if (detectedAnomaly) {
            detectedAnomalies++;
          } else {
            missedAnomalies++;
          }
        } else {
          if (detectedAnomaly) {
            falseAlarms++;
          }
        }
      } catch (error) {
        console.error('Erreur prédiction anomalie:', error);
      }
    }

    results.metrics = this.calculateAnomalyMetrics({
      correctPredictions,
      detectedAnomalies,
      actualAnomalies,
      missedAnomalies,
      falseAlarms,
      totalSamples: testData.length
    });

    this.validationResults.set(validationId, results);
    this.saveToStorage();

    return results;
  }

  /**
   * Simuler la prédiction d'anomalie (placeholder)
   */
  async predictAnomaly(model, sample) {
    const random = Math.random();
    return {
      hasAnomaly: random > 0.7,
      confidence: random
    };
  }

  /**
   * Calculer les métriques de détection d'anomalies
   */
  calculateAnomalyMetrics(metrics) {
    const { correctPredictions, detectedAnomalies, actualAnomalies, missedAnomalies, falseAlarms, totalSamples } = metrics;

    const accuracy = totalSamples > 0 ? (correctPredictions / totalSamples) * 100 : 0;
    const detectionRate = actualAnomalies > 0 ? (detectedAnomalies / actualAnomalies) * 100 : 0;
    const falseAlarmRate = totalSamples > 0 ? (falseAlarms / totalSamples) * 100 : 0;

    return {
      accuracy: accuracy.toFixed(2),
      detectionRate: detectionRate.toFixed(2),
      falseAlarmRate: falseAlarmRate.toFixed(2),
      detectedAnomalies,
      actualAnomalies,
      missedAnomalies,
      falseAlarms,
      correctPredictions,
      totalSamples
    };
  }

  /**
   * Benchmark des performances du modèle
   */
  async benchmarkModel(model, testIterations = 10) {
    const benchmarkId = this.generateId();
    const results = {
      id: benchmarkId,
      modelType: 'performance_benchmark',
      timestamp: new Date().toISOString(),
      iterations: testIterations,
      latencies: [],
      memoryUsage: [],
      metrics: {}
    };

    for (let i = 0; i < testIterations; i++) {
      const startTime = performance.now();
      
      // Simuler une prédiction
      await this.simulatePrediction(model);
      
      const endTime = performance.now();
      const latency = endTime - startTime;
      
      results.latencies.push(latency);
      
      // Simuler l'utilisation mémoire
      const memoryUsage = this.estimateMemoryUsage();
      results.memoryUsage.push(memoryUsage);
    }

    results.metrics = this.calculatePerformanceMetrics(results.latencies, results.memoryUsage);

    this.benchmarkResults.set(benchmarkId, results);
    this.saveToStorage();

    return results;
  }

  /**
   * Simuler une prédiction pour benchmark
   */
  async simulatePrediction(model) {
    // Simuler un temps de traitement
    await new Promise(resolve => setTimeout(resolve, Math.random() * 100));
  }

  /**
   * Estimer l'utilisation mémoire (simplifié)
   */
  estimateMemoryUsage() {
    if (performance.memory) {
      return performance.memory.usedJSHeapSize / 1024 / 1024; // MB
    }
    return Math.random() * 50 + 20; // Simulation
  }

  /**
   * Calculer les métriques de performance
   */
  calculatePerformanceMetrics(latencies, memoryUsage) {
    const avgLatency = latencies.reduce((a, b) => a + b, 0) / latencies.length;
    const minLatency = Math.min(...latencies);
    const maxLatency = Math.max(...latencies);
    const stdLatency = Math.sqrt(latencies.reduce((sum, lat) => sum + Math.pow(lat - avgLatency, 2), 0) / latencies.length);

    const avgMemory = memoryUsage.reduce((a, b) => a + b, 0) / memoryUsage.length;
    const maxMemory = Math.max(...memoryUsage);

    return {
      avgLatency: avgLatency.toFixed(2),
      minLatency: minLatency.toFixed(2),
      maxLatency: maxLatency.toFixed(2),
      stdLatency: stdLatency.toFixed(2),
      avgMemory: avgMemory.toFixed(2),
      maxMemory: maxMemory.toFixed(2),
      throughput: (1000 / avgLatency).toFixed(2) // prédictions par seconde
    };
  }

  /**
   * Générer un rapport de validation complet
   */
  generateValidationReport(validationId) {
    const validation = this.validationResults.get(validationId);
    if (!validation) {
      throw new Error('Validation non trouvée');
    }

    const report = {
      validation: validation,
      summary: this.generateValidationSummary(validation),
      recommendations: this.generateRecommendations(validation),
      timestamp: new Date().toISOString()
    };

    return report;
  }

  /**
   * Générer un résumé de validation
   */
  generateValidationSummary(validation) {
    const metrics = validation.metrics;
    
    if (validation.modelType === 'malaria_detection') {
      return {
        overall: `Accuracy: ${metrics.accuracy}%`,
        strengths: this.identifyStrengths(metrics),
        weaknesses: this.identifyWeaknesses(metrics),
        grade: this.calculateGrade(metrics)
      };
    } else if (validation.modelType === 'anomaly_detection') {
      return {
        overall: `Accuracy: ${metrics.accuracy}%`,
        detectionRate: `Détection: ${metrics.detectionRate}%`,
        falseAlarmRate: `Fausses alertes: ${metrics.falseAlarmRate}%`,
        grade: this.calculateAnomalyGrade(metrics)
      };
    }

    return { overall: 'Validation terminée' };
  }

  /**
   * Identifier les forces du modèle
   */
  identifyStrengths(metrics) {
    const strengths = [];
    
    if (parseFloat(metrics.accuracy) > 90) {
      strengths.push('Excellente précision globale');
    }
    if (parseFloat(metrics.precision) > 85) {
      strengths.push('Bonne précision des positifs');
    }
    if (parseFloat(metrics.recall) > 85) {
      strengths.push('Bonne détection des positifs');
    }
    if (parseFloat(metrics.specificity) > 85) {
      strengths.push('Bonne identification des négatifs');
    }

    return strengths.length > 0 ? strengths : ['Performance satisfaisante'];
  }

  /**
   * Identifier les faiblesses du modèle
   */
  identifyWeaknesses(metrics) {
    const weaknesses = [];
    
    if (parseFloat(metrics.precision) < 70) {
      weaknesses.push('Taux de fausses positifs élevé');
    }
    if (parseFloat(metrics.recall) < 70) {
      weaknesses.push('Taux de faux négatifs élevé');
    }
    if (parseFloat(metrics.specificity) < 70) {
      weaknesses.push('Mauvaise identification des négatifs');
    }
    if (metrics.falseNegatives > metrics.falsePositives * 2) {
      weaknesses.push('Bias vers les négatifs');
    }

    return weaknesses;
  }

  /**
   * Calculer une note globale (A-F)
   */
  calculateGrade(metrics) {
    const accuracy = parseFloat(metrics.accuracy);
    const f1Score = parseFloat(metrics.f1Score);
    
    const avgScore = (accuracy + f1Score) / 2;
    
    if (avgScore >= 95) return 'A';
    if (avgScore >= 90) return 'A-';
    if (avgScore >= 85) return 'B+';
    if (avgScore >= 80) return 'B';
    if (avgScore >= 75) return 'B-';
    if (avgScore >= 70) return 'C';
    if (avgScore >= 60) return 'D';
    return 'F';
  }

  /**
   * Calculer une note pour la détection d'anomalies
   */
  calculateAnomalyGrade(metrics) {
    const accuracy = parseFloat(metrics.accuracy);
    const detectionRate = parseFloat(metrics.detectionRate);
    const falseAlarmRate = parseFloat(metrics.falseAlarmRate);
    
    const score = accuracy - (falseAlarmRate / 2);
    
    if (score >= 90) return 'A';
    if (score >= 85) return 'A-';
    if (score >= 80) return 'B+';
    if (score >= 75) return 'B';
    if (score >= 70) return 'B-';
    if (score >= 65) return 'C';
    if (score >= 60) return 'D';
    return 'F';
  }

  /**
   * Générer des recommandations d'amélioration
   */
  generateRecommendations(validation) {
    const recommendations = [];
    const metrics = validation.metrics;

    if (validation.modelType === 'malaria_detection') {
      if (parseFloat(metrics.precision) < 80) {
        recommendations.push('Augmenter le nombre d\\'échantillons positifs dans le dataset');
        recommendations.push('Ajuster le seuil de classification');
      }
      if (parseFloat(metrics.recall) < 80) {
        recommendations.push('Améliorer la qualité des images d\\'entraînement');
        recommendations.push('Utiliser data augmentation pour les positifs');
      }
      if (metrics.falseNegatives > 5) {
        recommendations.push('Prioriser la réduction des faux négatifs (critique médical)');
      }
    } else if (validation.modelType === 'anomaly_detection') {
      if (parseFloat(metrics.falseAlarmRate) > 20) {
        recommendations.push('Ajuster les seuils de détection');
        recommendations.push('Améliorer la normalisation des données');
      }
      if (parseFloat(metrics.detectionRate) < 80) {
        recommendations.push('Enrichir le dataset avec plus d\\'anomalies');
      }
    }

    if (validation.testSize < 50) {
      recommendations.push('Augmenter la taille du dataset de test pour une validation plus robuste');
    }

    return recommendations;
  }

  /**
   * Comparer deux validations
   */
  compareValidations(validationId1, validationId2) {
    const validation1 = this.validationResults.get(validationId1);
    const validation2 = this.validationResults.get(validationId2);

    if (!validation1 || !validation2) {
      throw new Error('Validations non trouvées');
    }

    const comparison = {
      validation1: validation1,
      validation2: validation2,
      improvements: {},
      regressions: {},
      summary: ''
    };

    // Comparer les métriques
    Object.keys(validation1.metrics).forEach(metric => {
      const value1 = parseFloat(validation1.metrics[metric]);
      const value2 = parseFloat(validation2.metrics[metric]);

      if (!isNaN(value1) && !isNaN(value2)) {
        const diff = value2 - value1;
        
        if (diff > 0) {
          comparison.improvements[metric] = `+${diff.toFixed(2)}`;
        } else if (diff < 0) {
          comparison.regressions[metric] = `${diff.toFixed(2)}`;
        }
      }
    });

    // Générer un résumé
    const improvementCount = Object.keys(comparison.improvements).length;
    const regressionCount = Object.keys(comparison.regressions).length;

    if (improvementCount > regressionCount) {
      comparison.summary = 'Amélioration globale du modèle';
    } else if (regressionCount > improvementCount) {
      comparison.summary = 'Régression détectée - investigation requise';
    } else {
      comparison.summary = 'Performance stable';
    }

    return comparison;
  }

  /**
   * Obtenir l'historique des validations
   */
  getValidationHistory(modelType = null) {
    const history = Array.from(this.validationResults.values());
    
    if (modelType) {
      return history.filter(v => v.modelType === modelType);
    }
    
    return history.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  }

  /**
   * Obtenir les tendances de performance
   */
  getPerformanceTrends(modelType) {
    const history = this.getValidationHistory(modelType);
    
    if (history.length < 2) {
      return { trend: 'insufficient_data', data: [] };
    }

    const trends = {
      accuracy: [],
      timestamp: []
    };

    history.forEach(validation => {
      if (validation.metrics.accuracy) {
        trends.accuracy.push(parseFloat(validation.metrics.accuracy));
        trends.timestamp.push(new Date(validation.timestamp));
      }
    });

    // Calculer la tendance
    const recentAccuracy = trends.accuracy.slice(-5);
    const olderAccuracy = trends.accuracy.slice(0, -5);
    
    const recentAvg = recentAccuracy.reduce((a, b) => a + b, 0) / recentAccuracy.length;
    const olderAvg = olderAccuracy.reduce((a, b) => a + b, 0) / olderAccuracy.length;
    
    const trend = recentAvg > olderAvg ? 'improving' : 
                 recentAvg < olderAvg ? 'degrading' : 'stable';

    return {
      trend: trend,
      data: trends,
      recentAverage: recentAvg.toFixed(2),
      olderAverage: olderAvg.toFixed(2),
      change: (recentAvg - olderAvg).toFixed(2)
    };
  }

  /**
   * Générer un ID unique
   */
  generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substr(2);
  }

  /**
   * Exporter les résultats de validation
   */
  exportValidationResults(validationId) {
    const validation = this.validationResults.get(validationId);
    if (!validation) {
      throw new Error('Validation non trouvée');
    }

    const report = this.generateValidationReport(validationId);
    return JSON.stringify(report, null, 2);
  }

  /**
   * Supprimer une validation
   */
  deleteValidation(validationId) {
    this.validationResults.delete(validationId);
    this.saveToStorage();
  }
}

// Instance globale du validateur de modèles
const modelValidator = new ModelValidator();
