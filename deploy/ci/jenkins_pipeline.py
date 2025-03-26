#!/usr/bin/env python3
"""
Jenkins Pipeline Configuration Generator for the Trading Platform.

This script generates a Jenkinsfile with a complete CI/CD pipeline for the trading platform.
The pipeline includes stages for code checkout, environment setup, testing, building,
and deployment to various environments.

Usage:
    python jenkins_pipeline.py --output ./Jenkinsfile [--env production]

Options:
    --output: Path to save the generated Jenkinsfile
    --env: Target environment (development, staging, production)
"""

import argparse
import os
import sys
from textwrap import dedent


PIPELINE_TEMPLATE = """
pipeline {
    agent {
        docker {
            image 'python:3.9'
            args '-v /var/run/docker.sock:/var/run/docker.sock'
        }
    }

    environment {
        DOCKER_REGISTRY = 'registry.example.com'
        APP_NAME = 'trading-platform'
        DEPLOY_ENV = '${params.ENVIRONMENT}'
    }

    parameters {
        choice(name: 'ENVIRONMENT', choices: ['development', 'staging', 'production'], description: 'Deployment Environment')
        booleanParam(name: 'RUN_TESTS', defaultValue: true, description: 'Run Tests')
        booleanParam(name: 'BUILD_DOCKER', defaultValue: true, description: 'Build Docker Image')
        booleanParam(name: 'DEPLOY', defaultValue: true, description: 'Deploy Application')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Setup Environment') {
            steps {
                sh 'python -m pip install --upgrade pip'
                sh 'pip install -r requirements.txt'
                sh 'pip install -r requirements-dev.txt'
            }
        }

        stage('Lint') {
            steps {
                sh 'flake8 .'
                sh 'black --check .'
            }
        }

        stage('Test') {
            when {
                expression { return params.RUN_TESTS }
            }
            steps {
                sh 'pytest --cov=. --cov-report=xml tests/'
            }
            post {
                always {
                    junit 'test-results/*.xml'
                    cobertura coberturaReportFile: 'coverage.xml'
                }
            }
        }

        stage('Build Docker Image') {
            when {
                expression { return params.BUILD_DOCKER }
            }
            steps {
                sh 'docker build -t ${DOCKER_REGISTRY}/${APP_NAME}:${BUILD_NUMBER} -f deploy/docker/Dockerfile .'
                sh 'docker tag ${DOCKER_REGISTRY}/${APP_NAME}:${BUILD_NUMBER} ${DOCKER_REGISTRY}/${APP_NAME}:latest'
            }
        }

        stage('Push Docker Image') {
            when {
                expression { return params.BUILD_DOCKER }
            }
            steps {
                withCredentials([usernamePassword(credentialsId: 'docker-registry-credentials', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASSWORD')]) {
                    sh 'echo $DOCKER_PASSWORD | docker login ${DOCKER_REGISTRY} -u $DOCKER_USER --password-stdin'
                    sh 'docker push ${DOCKER_REGISTRY}/${APP_NAME}:${BUILD_NUMBER}'
                    sh 'docker push ${DOCKER_REGISTRY}/${APP_NAME}:latest'
                }
            }
        }

        stage('Deploy') {
            when {
                expression { return params.DEPLOY }
            }
            steps {
                script {
                    def kubeConfig
                    def namespace
                    
                    if (params.ENVIRONMENT == 'development') {
                        kubeConfig = 'kubeconfig-dev'
                        namespace = 'trading-platform-dev'
                    } else if (params.ENVIRONMENT == 'staging') {
                        kubeConfig = 'kubeconfig-staging'
                        namespace = 'trading-platform-staging'
                    } else if (params.ENVIRONMENT == 'production') {
                        kubeConfig = 'kubeconfig-prod'
                        namespace = 'trading-platform-prod'
                        
                        // Additional approval step for production
                        input message: 'Deploy to production?', ok: 'Deploy'
                    }
                    
                    withKubeConfig([credentialsId: kubeConfig]) {
                        sh '''
                        sed -i "s|{{IMAGE_TAG}}|${BUILD_NUMBER}|g" deploy/kubernetes/deployment.yaml
                        kubectl apply -f deploy/kubernetes/configmap.yaml -n ${namespace}
                        kubectl apply -f deploy/kubernetes/service.yaml -n ${namespace}
                        kubectl apply -f deploy/kubernetes/deployment.yaml -n ${namespace}
                        '''
                    }
                }
            }
        }
    }

    post {
        always {
            cleanWs()
        }
        success {
            slackSend(color: 'good', message: "Build ${env.BUILD_NUMBER} succeeded! Application deployed to ${params.ENVIRONMENT}")
        }
        failure {
            slackSend(color: 'danger', message: "Build ${env.BUILD_NUMBER} failed! Check logs: ${env.BUILD_URL}")
        }
    }
}
"""


def generate_jenkinsfile(output_path):
    """Generate a Jenkinsfile at the specified path."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w') as f:
        f.write(dedent(PIPELINE_TEMPLATE.strip()))
    
    print(f"Jenkinsfile generated at {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Generate a Jenkinsfile for the trading platform')
    parser.add_argument('--output', required=True, help='Output path for the Jenkinsfile')
    parser.add_argument('--env', default='development', choices=['development', 'staging', 'production'],
                        help='Target deployment environment')
    
    args = parser.parse_args()
    
    try:
        generate_jenkinsfile(args.output)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())