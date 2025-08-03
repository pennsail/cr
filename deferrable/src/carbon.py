from numpy import array
import numpy as np
import pandas as pd
from pandas.core.frame import DataFrame

class CarbonModel():
    def __init__(self, name, df: DataFrame, carbon_start_index, carbon_error) -> None:
        self.name = name
        self.df = df
        self.carbon_start_index = carbon_start_index
        self.carbon_error = carbon_error
        self.mean = self.df["carbon_intensity_avg"].mean()
        self.std = self.df["carbon_intensity_avg"].std()

    def reindex(self, index):
        df = self.df[index:].copy().reset_index()
        model = CarbonModel(self.name, df, self.carbon_start_index, self.carbon_error)
        return model

    def subtrace(self, start_index, end_index):
        df = self.df[start_index: end_index].copy().reset_index()
        model = CarbonModel(self.name, df,self.carbon_start_index, self.carbon_error)
        return model
    
    def extend(self, factor):
        df = pd.DataFrame(np.repeat(self.df.values, factor, axis=0), columns=["carbon_intensity_avg"])
        df["carbon_intensity_avg"] /= factor
        model = CarbonModel(self.name, df,self.carbon_start_index, self.carbon_error)
        return model

    def __getitem__(self, index):
        return self.df.iloc[index]['carbon_intensity_avg']

def get_carbon_model(carbon_trace:str, carbon_start_index:int, carbon_error="ORACLE") -> CarbonModel:
    df = pd.read_csv(f"src/traces/{carbon_trace}.csv")
    df = df[17544+carbon_start_index:17544+carbon_start_index+720]
    df = df[["carbon_intensity_avg"]]
    df["carbon_intensity_avg"] /= 1000
    c = CarbonModel(carbon_trace, df, carbon_start_index, carbon_error)
    return c

def get_carbon_model_from_array(arr, carbon_error="CUSTOM"):
    """
    Build a CarbonModel directly from a 1-D array of hourly intensities.
    """
    import pandas as pd
    from pandas import DataFrame

    df = pd.DataFrame({"carbon_intensity_avg": arr})
    return CarbonModel("from_array", df, carbon_start_index=0, carbon_error=carbon_error)

def get_custom_carbon_model(carbon_start_index:int, carbon_error="ORACLE") -> CarbonModel:
    # put your custom carbon intensity values here
    ci = np.ones(48) * 100  # Example: 48 hours of constant carbon intensity at 100 gCO2/kWh
    
    repeated_ci = np.tile(ci, 30)
    df = pd.DataFrame({"carbon_intensity_avg": repeated_ci})
    df["carbon_intensity_avg"] /= 1000
    
    c = CarbonModel("custom", df, carbon_start_index, carbon_error)
    return c