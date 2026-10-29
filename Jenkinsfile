pipeline {
  agent docker

  environment {
    RELEASE = sh(script: "date +%Y-%m-%d_%H%M%S", returnStdout: true).trim()
    TARGET = "root@172.19.66.226"
    BASEDIR = "/root/docker-compose/LLM"
  }

  stages {

    stage('Checkout') {
      steps {
        git branch: develop , url: 'http://172.31.65.214/nrdc/ai/nlp/sources/llm-agent.git',
                    credentialsId: 'gitlab_softwareg_token'
        }
    }

    stage('Archive Release') {
      steps {
        sh """
        mkdir build
        tar czf build/release-${RELEASE}.tar.gz agent ui configs
        """
      }
    }

    stage('Transfer') {
      steps {
        sh """
        scp build/release-${RELEASE}.tar.gz ${TARGET}:${BASEDIR}/
        """
      }
    }

    stage('Deploy') {
      steps {
        sh """
        ssh ${TARGET} '
          cd ${BASEDIR}

          mkdir -p releases/${RELEASE}

          tar xzf release-${RELEASE}.tar.gz -C releases/${RELEASE}

          ln -sfn releases/${RELEASE} current

          ./deploy.sh
        '
        """
      }
    }

    stage('Cleanup') {
      steps {
        sh """
        ssh ${TARGET} '
          cd ${BASEDIR}/releases
          ls -1dt */ | tail -n +6 | xargs -r rm -rf
        '
        """
      }
    }
  }
}