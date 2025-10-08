# Project Readme

This document provides a detailed overview of the project structure, datasets, and the code used for analysis and data collection.

## 1. Project Overview

We present the first systematic advertiser-level audit of children’s
video advertising, analyzing 22,760 ad impressions from 2,928 ad-
vertisers across 30 countries. Advertiser characteristics, verifica-
tion status, geographic origin, and cross-border targeting emerge
as critical yet overlooked predictors of ad safety: in regions with
weaker online child-protection policy, unverified advertisers are
3–4× more likely to serve age-inappropriate ads, and specific source
countries (notably Ecuador and Lebanon) disproportionately supply
age-inappropriate ads to vulnerable Arab and South Asian audi-
ences, pointing to advertiser-focused interventions as essential. We
also provide cross-regional evidence linking policy to safety out-
comes: children in regions with weaker regulation face ∼3.6× more
inappropriate exposure, reflecting weaker verification enforcement,
language-specific risks, and regulatory gaps. Finally, a metadata-
only baseline (Random Forest) attains 84.9% accuracy and 76.9%
F1 for automated appropriateness detection, indicating feasibility
for scalable, advertiser-aware moderation. To support reproducible
research, we release a corpus of 5,611 video ads with qualitative
labels for age appropriateness and relevance.

## 2. Directory Structure

The project is organized into three main folders: `Code`, `Data` and `Classifier`.

```
.
├── Code/
│   ├── Analysis/
│   │   ├── analysis.ipynb
│   │   └── robustness_check.ipynb
│   └── Crawler/
│       └── script.py
├── Data/
│   ├── videos_dataset.csv
│   ├── labeled_sample.csv
│   ├── ad_metadata.csv
│   └── main_videos.csv
└── Classifier/
    ├── classifier.ipynb
    ├── requirements.txt
    ├── README.md
    ├── plots/
    │   └── (contains generated figures and plots)
    └── models/
        └── (contains saved model files)
```

## 3. Data

The `Data` folder contains all the datasets used in this project.

### **3.1 `videos_dataset.csv`**

This is the main dataset containing 22,766 cleaned ad impressions.

*   **Relevant Columns:**
    *   `Main Video Details`: Information about the main video hosting the ad.
    *   `Main Video ID`: Unique identifier for the main video.
    *   `Country`: The country where the ad impression was recorded.
    *   `Video Ads`: Details about the video ad.
    *   `Ad ID`: Unique identifier for the ad.
    *   `Advertiser Name`: The name of the advertiser.
    *   `Advertiser Location`: The geographical location of the advertiser.
    *   `Verified`: A boolean indicating if the advertiser is verified.
    *   `ad_id_clean`: A cleaned version of the ad ID.
    *   `main_id_clean`: A cleaned version of the main video ID.
    
    > **Note:** The advertiser attributes (`Advertiser Name`, `Advertiser Location`, `Verified`) are central to our analysis.

### **3.2 `labeled_sample.csv`**

This dataset consists of 5,611 ad samples that have been manually annotated by two annotators to reach a consensus.

*   **Relevant Columns:**
    *   `Main Video Details`, `Main Video ID`, `Country`, `Video Ads`, `Ad ID`: Same as above.
    *   `primary_tag`: The main classification of the ad, which can be `inappropriate`, `child-directed`, `irrelevant`, or `ambiguous`.
    *   `secondary_tag`: Provides a more detailed explanation for the assigned `primary_tag`.

### **3.3 `ad_metadata.csv`**

This file contains additional metadata for the ad IDs present in the `labeled_sample.csv`.

*   **Relevant Columns:**
    *   `Category Name`: The category of the ad.
    *   `Language`: The language of the ad.

### **3.4 `main_videos.csv`**

This dataset contains information about the top 25 videos from the top 100 "Made for Kids" channels, as ranked by Social Blade.

*   **Relevant Columns:**
    *   `channel_id`: Unique identifier for the channel.
    *   `video_id`: Unique identifier for the video.
    *   `video_title`: The title of the video.
    *   `length`: The duration of the video.
    *   `upload_date`: The date the video was uploaded.
    *   `views`: Total number of views.
    *   `is_short`: A flag to indicate if the video is a YouTube Short.
    *   `rank`: The ranking of the video.

## 4. Code

The `Code` folder is divided into `Analysis` and `Crawler`.

### **4.1 `Code/Analysis`**

This directory contains the Jupyter Notebooks used for data analysis.

*   **`analysis.ipynb`**: This notebook utilizes the datasets in the `Data` folder to generate all the plots and visualizations presented in the main paper.
*   **`robustness_check.ipynb`**: This notebook performs a robustness check on the advertiser analysis using the complete `videos_dataset.csv`.

### **4.2 `Code/Crawler`**

This directory contains the web scraping script.

*   **`script.py`**: This is the main script for scraping advertisements.
    *   **Functionality**:
        *   Works for both EU and non-EU regions.
        *   Automatically accepts cookie banners.
        *   Scrapes all advertisements shown in the main video, including video ads and advertiser details.
        *   Captures end-screen recommendations and any external links.
    *   **Setup**:
        *   Ensure that the version of ChromeDriver is compatible with the Chrome browser installed on your system.
    *   **Usage**:
        *   The script is run via the command line with two arguments:
            1.  The file name containing a list of video IDs to be processed.
            2.  A unique profile directory path. This is required to run multiple threads simultaneously.

        ```bash
        python script.py [video_ids_file] [profile_directory]
        ```

## 5. Classifier

The `Classifier` folder contains all code and instructions for running the automated ad appropriateness classifier.

1. The classifier is implemented in a Jupyter notebook (`classifier.ipynb`) using Python.
2. All required dependencies are listed in `requirements.txt` for easy installation.
3. Running the notebook takes approximately 3-5 minutes for a complete run.
4. All evaluation results and performance metrics are presented within the notebook.
