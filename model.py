import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import joblib
import matplotlib.pyplot as plt

# 1. Load Data
df = pd.read_csv("xgboost_training_data_with_population.csv")
df = df[df['utci_c'] >= 32.0]
cols_to_drop = ['census_ward_number', 'actual_hospitalizations']

features = [
        'ward_elderly_pct', 'child_pct', 'slum_pct', 
        'temp_c', 'humidity', 'wind_speed', 'solar_radiation', 
        'precipitation_mm', 'is_day', 'wet_bulb_c', 'utci_c', 'cumul_utci_stress', 'total_population'
    ]

target = 'actual_hospitalizations'  # Predicting actual hospitalizations directly

X = df[features]
y = df[target]


# 3. Train/Test Split (80% Training, 20% Validation)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 4. Define the XGBoost Regressor
# Using count:poisson because the target variable represents discrete counts (hospital admissions)
xgb_model = xgb.XGBRegressor(
objective='count:poisson', 
    eval_metric='poisson-nloglik', # Better metric for Poisson
    learning_rate=0.05,
    max_depth=6,
    random_state=42
)

# 5. Hyperparameter Grid
# Focused grid to run efficiently during a hackathon
param_grid = {
    'n_estimators': [100, 200, 300],
    'learning_rate': [0.01, 0.05, 0.1],
    'max_depth': [4, 6, 8],
    'subsample': [0.8, 1.0],
    'colsample_bytree': [0.8, 1.0]
}

# 6. Grid Search Optimization
print("Starting Hyperparameter Optimization (this may take a few minutes)...")
grid_search = GridSearchCV(
    estimator=xgb_model,
    param_grid=param_grid,
    cv=3,           # 3-fold cross-validation
    scoring='neg_mean_absolute_error', 
    verbose=1,
    n_jobs=-1       # Uses all available CPU cores
)

grid_search.fit(X_train, y_train)

print("5. Evaluating Model Performance...")
y_pred = grid_search.predict(X_test)
r2 = r2_score(y_test, y_pred)
mae = mean_absolute_error(y_test, y_pred)
rmse = np.sqrt(mean_squared_error(y_test, y_pred))

print("\n" + "="*40)
print(" 📊 MODEL PERFORMANCE SUMMARY")
print("="*40)
print(f"R-Squared (R2)      : {r2:.4f}")
print(f"Mean Absolute Error : {mae:.4f}")
print(f"Root Mean Sq Error  : {rmse:.4f}")
print("="*40)

# 7. Evaluate the Best Model
best_model = grid_search.best_estimator_
print(f"\nBest Hyperparameters Found: {grid_search.best_params_}")

predictions = best_model.predict(X_test)
mae = mean_absolute_error(y_test, predictions)
rmse = np.sqrt(mean_squared_error(y_test, predictions))

print(f"Validation Mean Absolute Error (MAE): {mae:.2f} patients")
print(f"Validation Root Mean Squared Error (RMSE): {rmse:.2f} patients")

# 8. Export the Model for risk_engine.py
model_filename = "heat_risk_xgboost_model.pkl"
joblib.dump(best_model, model_filename)
print(f"Model saved successfully as '{model_filename}'")

# 9. Extract and Plot Feature Importance (Crucial for Hackathon Pitch)
feature_importances = best_model.feature_importances_
importance_df = pd.DataFrame({
    'Feature': X.columns,
    'Importance': feature_importances
}).sort_values(by='Importance', ascending=True)

plt.figure(figsize=(10, 6))
plt.barh(importance_df['Feature'], importance_df['Importance'], color='darkorange')
plt.title("XGBoost Feature Importance: Heat-Health Risk Drivers")
plt.xlabel("Relative Importance Score")
plt.tight_layout()
plt.savefig("feature_importance_chart.png")
print("Feature importance chart saved as 'feature_importance_chart.png'")