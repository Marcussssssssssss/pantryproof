import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.pantryproof.prototype"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.pantryproof.prototype"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        testInstrumentationRunnerArguments["clearPackageData"] = "true"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }

        create("s04Fake") {
            initWith(getByName("debug"))
            applicationIdSuffix = ".s04fake"
        }

        create("t09Live") {
            initWith(getByName("debug"))
            applicationIdSuffix = ".t09live"
        }
    }

    if (gradle.startParameter.projectProperties["s04FakeInstrumentation"] == "true") {
        testBuildType = "s04Fake"
    } else if (gradle.startParameter.projectProperties["t09LiveInstrumentation"] == "true") {
        testBuildType = "t09Live"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        execution = "ANDROIDX_TEST_ORCHESTRATOR"
    }

    sourceSets.getByName("androidTest").assets.srcDir(
        rootProject.file("../../tests/fixtures/receipt_presentation_v1/review_v1"),
    )
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    implementation("androidx.activity:activity-ktx:1.9.0")
    implementation("com.fasterxml.jackson.core:jackson-core:2.21.8")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test:runner:1.7.0")
    androidTestImplementation("androidx.test.ext:junit-ktx:1.3.0")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.7.0")
    androidTestImplementation("androidx.test.espresso:espresso-intents:3.7.0")
    androidTestUtil("androidx.test:orchestrator:1.6.1")
}
