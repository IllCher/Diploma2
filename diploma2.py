# -*- coding: utf-8 -*-
#Загрузка данных с kaggle

import os
import sys
from tempfile import NamedTemporaryFile
from urllib.request import urlopen
from urllib.parse import unquote, urlparse
from urllib.error import HTTPError
from zipfile import ZipFile
import tarfile
import shutil

CHUNK_SIZE = 40960
DATA_SOURCE_MAPPING = 'daily-climate-time-series-data:https%3A%2F%2Fstorage.googleapis.com%2Fkaggle-data-sets%2F312121%2F636393%2Fbundle%2Farchive.zip%3FX-Goog-Algorithm%3DGOOG4-RSA-SHA256%26X-Goog-Credential%3Dgcp-kaggle-com%2540kaggle-161607.iam.gserviceaccount.com%252F20240606%252Fauto%252Fstorage%252Fgoog4_request%26X-Goog-Date%3D20240606T113419Z%26X-Goog-Expires%3D259200%26X-Goog-SignedHeaders%3Dhost%26X-Goog-Signature%3D7f36352c4618158e4aeeb770dc68d1788fa461c91d0936d39f1746d181a5b7a3f5b13b3136a49472daebdc13e49ff43fadb7a61213e649a0e05091cc9499fa8a8ca551fafc8403d4afa10fc685eee5a0fbc103615cd6f68571c4284d6e1557c25c67736f5f24e539bc0cd01d23c933db54f77ab1fe4e4be9280dea11609db5e378738cae4c5bd4fdc15a7ae1bd58acd6c0163c9e1c4645488de695a305ee1161069b581f07448c395a6b972f0cfb5c84a950c6245a0a25b69ecdf21def25e3a62ed11f21cdaf3f530e104ed072cf877b2de3d8801bd3af26d0b7d4ecad6e4674d82607477fcc76a2bc8da95bcacddfc62eea66bb72795e2395f87806d5528d70'

KAGGLE_INPUT_PATH='/kaggle/input'
KAGGLE_WORKING_PATH='/kaggle/working'
KAGGLE_SYMLINK='kaggle'

!umount /kaggle/input/ 2> /dev/null
shutil.rmtree('/kaggle/input', ignore_errors=True)
os.makedirs(KAGGLE_INPUT_PATH, 0o777, exist_ok=True)
os.makedirs(KAGGLE_WORKING_PATH, 0o777, exist_ok=True)

try:
  os.symlink(KAGGLE_INPUT_PATH, os.path.join("..", 'input'), target_is_directory=True)
except FileExistsError:
  pass
try:
  os.symlink(KAGGLE_WORKING_PATH, os.path.join("..", 'working'), target_is_directory=True)
except FileExistsError:
  pass

for data_source_mapping in DATA_SOURCE_MAPPING.split(','):
    directory, download_url_encoded = data_source_mapping.split(':')
    download_url = unquote(download_url_encoded)
    filename = urlparse(download_url).path
    destination_path = os.path.join(KAGGLE_INPUT_PATH, directory)
    try:
        with urlopen(download_url) as fileres, NamedTemporaryFile() as tfile:
            total_length = fileres.headers['content-length']
            print(f'Downloading {directory}, {total_length} bytes compressed')
            dl = 0
            data = fileres.read(CHUNK_SIZE)
            while len(data) > 0:
                dl += len(data)
                tfile.write(data)
                done = int(50 * dl / int(total_length))
                sys.stdout.write(f"\r[{'=' * done}{' ' * (50-done)}] {dl} bytes downloaded")
                sys.stdout.flush()
                data = fileres.read(CHUNK_SIZE)
            if filename.endswith('.zip'):
              with ZipFile(tfile) as zfile:
                zfile.extractall(destination_path)
            else:
              with tarfile.open(tfile.name) as tarfile:
                tarfile.extractall(destination_path)
            print(f'\nDownloaded and uncompressed: {directory}')
    except HTTPError as e:
        print(f'Failed to load (likely expired) {download_url} to path {destination_path}')
        continue
    except OSError as e:
        print(f'Failed to load {download_url} to path {destination_path}')
        continue

print('Data source import complete.')

#Начало кода проекта

!pip install torchdiffeq
!pip install torchviz
!pip install pmdarima
import sys
from torchdiffeq import odeint_adjoint as odeadj
import numpy as np
import pandas as pd
import torch
import warnings
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.stattools import adfuller
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from sklearn.preprocessing import StandardScaler
from torch.utils.data import Dataset, DataLoader
from torch import nn
from sklearn.metrics import mean_absolute_error
import time
from pympler import asizeof
from torchviz import make_dot
import pmdarima as pm

warnings.filterwarnings("ignore")

def memory_usage(model):
  mem_params = sum([param.nelement()*param.element_size() for param in model.parameters()])
  mem_bufs = sum([buf.nelement()*buf.element_size() for buf in model.buffers()])
  mem = mem_params + mem_bufs
  return mem

def model_summary(model):
  print("model_summary")
  print()
  print("Layer_name"+"\t"*7+"Number of Parameters")
  print("="*100)
  model_parameters = [layer for layer in model.parameters() if layer.requires_grad]
  layer_name = [child for child in model.children()]
  j = 0
  total_params = 0
  print("\t"*10)
  for i in layer_name:
    #print()
    param = 0
    try:
      bias = (i.bias is not None)
    except:
      bias = False
    if not bias:
      param =model_parameters[j].numel()+model_parameters[j+1].numel()
      j = j+2
    else:
      param =model_parameters[j].numel()
      j = j+1
    print(str(i)+"\t"*3+str(param))
    total_params+=param
  print("="*100)
  print(f"Total Params:{total_params}")
  return total_params

"""# Подготовка данных"""

train = pd.read_csv("/kaggle/input/daily-climate-time-series-data/DailyDelhiClimateTrain.csv", parse_dates=['date'])
test = pd.read_csv("/kaggle/input/daily-climate-time-series-data/DailyDelhiClimateTest.csv", parse_dates=['date'])
test.head()

train.describe()

train.info()

train = train.iloc[:-1, :]
train.tail()

def plot_box_fts(train):
    fig = make_subplots(rows=2, cols=2)
    fig.add_trace(
        go.Box(y=train["humidity"], name="Влажность"),
        row=1, col=1
    )
    fig.add_trace(
        go.Box(y=train["wind_speed"], name="Скорость ветра"),
        row=1, col=2
    )
    fig.add_trace(
        go.Box(y=train["meanpressure"], name="Среднее давление"),
        row=2, col=1
    )
    fig.add_trace(
        go.Box(y=train["meantemp"], name="Средняя температура"),
        row=2, col=2
    )
    fig.update_layout(showlegend=False)
    fig.show()

plot_box_fts(train)

def get_outlier_iqr_limits(data, column, qr1=0.25, qr3=0.75):
    quartile1 = data[column].quantile(qr1)
    quartile3 = data[column].quantile(qr3)
    iqr = quartile3 - quartile1
    low, up = quartile1 - 1.5 * iqr, quartile3 + 1.5 * iqr
    return low, up
def replace_outliers(data, columns):
    for column in columns:
        low, up = get_outlier_iqr_limits(data, column)
        data[column] = np.where(data[column] < low, low,
            np.where(data[column] > up, up, data[column])
        )
    return data

train = replace_outliers(train, ["humidity", "wind_speed", "meanpressure", "meantemp"])
test = replace_outliers(test, ["humidity", "wind_speed", "meanpressure", "meantemp"]) #should?

plot_box_fts(train)

train = train.set_index("date")

"""# Обучение и тестирование"""

df = pd.concat([train, test.set_index("date")])
fts = {}
forecast_lead = 1
df_tmp = df.copy()
leadings = []
dfs = []
for tgt_col in ["humidity", "wind_speed", "meanpressure", "meantemp"]:
    df_in = df_tmp.copy()
    fts.update({tgt_col: list(df_tmp.columns.difference([tgt_col]))})
    tgt = f"{tgt_col}{forecast_lead}"
    leadings.append(tgt)
    df_in[tgt] = df_in[tgt_col].shift(-forecast_lead)
    dfs.append(df_in.iloc[:-forecast_lead])

test_start = "2016-01-01"

df_data = []

for df in dfs:
    df_train = df.loc[:test_start].iloc[:-1].copy()
    print()
    df_test = df.loc[test_start:].copy()
    df_data.append([df_train, df_test])

    print(f"Train size: {len(df_train)}")
    print(f"Test size: {len(df_test)}")

    print(f"Test fraction: {len(df_test) / len(df)}")

    scaler = StandardScaler()

    df_data[-1].append(scaler)

    init_columns = df.columns

    df_data[-1][0] = pd.DataFrame(scaler.fit_transform(df_train), columns=init_columns)
    df_data[-1][1] = pd.DataFrame(scaler.transform(df_test), columns=init_columns)

    print(df_train.head(3))

sarimax_temp = ARIMA(df_train["meantemp"], order=(1, 1, 1), seasonal_order=(1, 1, 0, 365))
sarimax_hum = ARIMA(df_train["humidity"], order=(1, 1, 1), seasonal_order=(1, 1, 0, 365))
sarimax_pres = ARIMA(df_train["meanpressure"], order=(1, 1, 1), seasonal_order=(1, 1, 0, 365))
sarimax_wind = ARIMA(df_train["wind_speed"], order=(1, 1, 1), seasonal_order=(1, 1, 0, 365))

'''
!pip install pmdarima
import pmdarima as pm

sarimax_temp = pm.auto_arima(df_train["meantemp"], start_p=1, start_q=1,test='adf',
                         max_p=3, max_q=3, m=365,
                         start_P=0, seasonal=True,
                         d=None, D=1, trace=True,
                         error_action='ignore',
                         suppress_warnings=True,
                         stepwise=True)'''

end_time = 0

start_time = time.time()
sarimax_temp = ARIMA(df_train["meantemp"], order=(1, 1, 1), seasonal_order=(1, 1, 0, 365))
sarimax_res_temp = sarimax_temp.fit(method='innovations_mle', low_memory=True, cov_type='none')
end_time += time.time() - start_time
print("SARIMA тренировка temp: ", end_time)
end_time = 0

start_time = time.time()
sarimax_hum = ARIMA(df_train["humidity"], order=(1, 1, 1), seasonal_order=(1, 1, 0, 365))
sarimax_res_hum = sarimax_hum.fit(method='innovations_mle', low_memory=True, cov_type='none')
end_time += time.time() - start_time
print("SARIMA тренировка hum: ", end_time)
end_time = 0

start_time = time.time()
sarimax_pres = ARIMA(df_train["meanpressure"], order=(1, 1, 1), seasonal_order=(1, 1, 0, 365))
sarimax_res_pres = sarimax_pres.fit(method='innovations_mle', low_memory=True, cov_type='none') #disp=False
end_time += time.time() - start_time
print("SARIMA тренировка pres: ", end_time)
end_time = 0

start_time = time.time()
sarimax_wind = ARIMA(df_train["wind_speed"], order=(1, 1, 1), seasonal_order=(1, 1, 0, 365))
sarimax_res_wind = sarimax_wind.fit(method='innovations_mle', low_memory=True, cov_type='none')
end_time += time.time() - start_time
print("SARIMA тренировка wind: ", end_time)
end_time = 0

start_time = time.time()
sarimax_pred_temp = sarimax_res_temp.predict(start=df_test.index.min(), end=df_test.index.max(), dynamic=True) #(start=df_test["date"].min(), end=df_test["date"].max(), dynamic=True)
end_time += time.time() - start_time
print("SARIMA тест wind: ", end_time)
end_time = 0
start_time = time.time()
sarimax_pred_hum = sarimax_res_hum.predict(start=df_test.index.min(), end=df_test.index.max(), dynamic=True)
end_time += time.time() - start_time
print("SARIMA тест wind: ", end_time)
end_time = 0
start_time = time.time()
sarimax_pred_pres = sarimax_res_pres.predict(start=df_test.index.min(), end=df_test.index.max(), dynamic=True)
end_time += time.time() - start_time
print("SARIMA тест wind: ", end_time)
end_time = 0
start_time = time.time()
sarimax_pred_wind = sarimax_res_wind.predict(start=df_test.index.min(), end=df_test.index.max(), dynamic=True)
end_time += time.time() - start_time
print("SARIMA тест wind: ", end_time)
end_time = 0

temp_concated = pd.concat([sarimax_res_temp.fittedvalues, sarimax_pred_temp])
hum_concated = pd.concat([sarimax_res_hum.fittedvalues, sarimax_pred_hum])
pres_concated = pd.concat([sarimax_res_pres.fittedvalues, sarimax_pred_pres])
wind_concated = pd.concat([sarimax_res_wind.fittedvalues, sarimax_pred_wind])

class SDS(Dataset):
    def __init__(self, df, tgt, fts, lngt=7):
        self.fts = fts
        self.tgt = tgt
        self.lngt = lngt
        self.x = torch.tensor(df[fts].values).float()
        self.y = torch.tensor(df[tgt].values).float()

    def __len__(self):
        return self.x.shape[0]

    def __getitem__(self, idx):
        if idx >= self.lngt - 1:
            idx_start = idx - self.lngt + 1
            x = self.x[idx_start:(idx + 1), :]
        else:
            padding = self.x[0].repeat(self.lngt - idx - 1, 1)
            x = self.x[0:(idx + 1), :]
            x = torch.cat((padding, x), 0)

        return x, self.y[idx]

class LSTM(nn.Module):
    def __init__(self, fts_cnt, hidden_sz):
        super().__init__()
        self.fts_cnt = fts_cnt
        self.hidden_sz = hidden_sz
        self.num_layers = 1

        self.lstm = nn.LSTM(
            input_size=fts_cnt,
            hidden_size=hidden_sz,
            num_layers=self.num_layers,
            batch_first=True,
        )

        self.linear = nn.Linear(in_features=self.hidden_sz, out_features=1)

    def forward(self, x):
        b_size = x.shape[0]
        h0 = torch.zeros(self.num_layers, b_size, self.hidden_sz).requires_grad_()
        c0 = torch.zeros(self.num_layers, b_size, self.hidden_sz).requires_grad_()

        output, (h_n, c_n) = self.lstm(x, (h0, c0))
        res = self.linear(h_n[0]).squeeze()
        return res

class f(nn.Module):
    def __init__(self, dim):
        super(f, self).__init__()
        self.model = nn.Sequential(
            nn.Linear(dim, dim),
            nn.ReLU(),
            nn.Linear(dim, dim),
            nn.Tanh()
        )

    def forward(self, t, x):
        return self.model(x)

class ODEBlock(nn.Module):
    def __init__(self, f):
        super(ODEBlock, self).__init__()
        self.f = f
        self.integration_time = torch.Tensor([0, 1]).float()

    def forward(self, x):
        self.integration_time = self.integration_time.type_as(x)
        tol = 0.25 #0.25
        out = odeadj(self.f, x, self.integration_time, rtol = tol, atol = tol)
        return out[1]

class ODENet(nn.Module):
    def __init__(self, fts_cnt, hidden_sz):
        super(ODENet, self).__init__()
        self.fc1 = nn.Linear(fts_cnt, hidden_sz)
        self.relu1 = nn.ReLU()
        self.ode_block = ODEBlock(f(dim=hidden_sz))
        self.fc2 = nn.Linear(hidden_sz, 1)

    def forward(self, x):
        batch_size = x.shape[0]
        x = x.view(batch_size, -1)

        out = self.fc1(x)
        out = self.relu1(out)
        out = self.ode_block(out)
        out = self.fc2(out).squeeze()

        return out

def make_predictions(loader, model):
    outputs = torch.tensor([])
    model.eval()
    with torch.inference_mode():
        for x, y in loader:
            pred = model(x)
            outputs = torch.cat((outputs, pred), 0)
    return outputs.numpy()

from pympler import asizeof
#torch.manual_seed(42)
#"humidity", "wind_speed", "meanpressure", "meantemp"
batch_size = 113#5
lngt = 14

hidden_size = 16
lr = 1e-3 #1e-3


epochs = 50 #7

predictions = {}

LSTMn = LSTM(3, 32)
NeuralODE = ODENet(42, 32)

models = [{"name": "LSTM", "model": LSTMn, "params": [], "memory": [], "other_memory": [], "hwpt_train": [], "hwpt_test": []},
         {"name": "ODENET", "model": NeuralODE, "params": [], "memory": [], "other_memory": [], "hwpt_train": [], "hwpt_test": []}]

for mdl in models:
    flag = True

    predictions[mdl["name"]] = {}
    for idx, lead in enumerate(leadings):
        train_dataset = SDS(
            df_data[idx][0],
            tgt=lead,
            fts=fts[lead[:-1]],
            lngt=lngt
        )
        test_dataset = SDS(
            df_data[idx][1],
            tgt=lead,
            fts=fts[lead[:-1]],
            lngt=lngt
        )

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)
        x, y = next(iter(train_loader))
        model = mdl["model"]
        loss_fn = nn.MSELoss()
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)

        test_loss_global = []

        end_time_train = 0

        for epoch in range(epochs):

            start_time_train = time.time()

            train_loss = []
            model.train()
            for x, y in train_loader:
                out = model(x)
                if flag:
                    make_dot(out, params=dict(model.named_parameters())).render("test_" + mdl["name"], format="png")
                    flag = False
                loss = loss_fn(out, y)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                train_loss.append(loss.item())

            end_time_train += time.time() - start_time_train

            test_loss = []
            model.eval()
            with torch.inference_mode():
                for x, y in test_loader:
                    out = model(x)
                    loss = loss_fn(out, y)
                    test_loss.append(loss.item())

            mean_loss_test = np.mean(test_loss)

        params = model_summary(model)
        memory = memory_usage(model)

        df_train_final = pd.DataFrame(df_data[idx][2].inverse_transform(df_data[idx][0]), columns=df_data[idx][0].columns)
        df_test_final = pd.DataFrame(df_data[idx][2].inverse_transform(df_data[idx][1]), columns=df_data[idx][1].columns)
        train_eval_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=False)
        pred_column = "prediction"

        start_time_test = time.time()

        df_train_final[pred_column] = make_predictions(train_eval_loader, model)
        df_test_final[pred_column] = make_predictions(test_loader, model)

        end_time_test = time.time() - start_time_test

        df_all_concat = pd.concat([df_train_final, df_test_final])
        df_all_concat[pred_column] = df_all_concat[pred_column] * df_data[idx][2].scale_[-1] + df_data[idx][2].mean_[-1]
        df_all_concat = df_all_concat.set_index(df.index)
        predictions[mdl["name"]].update({lead[:-1]: df_all_concat})

        mdl["params"].append(params)
        mdl["memory"].append(memory)
        mdl["hwpt_train"].append(end_time_train)
        mdl["hwpt_test"].append(end_time_test)
        mdl["other_memory"].append(asizeof.asizeof(model))

#pres_concated['2014-01-1'] = 1016.522324
#pres_concated['2013-01-1'] = 1014.678912
#hum_concated['2013-01-1'] = 80.522324
#temp_concated['2013-01-1'] = 12.348657
#wind_concated['2013-01-1'] = 5.947657

! pip install torchview
! pip install graphviz
from torchview import draw_graph

! pip install torchview
! pip install graphviz
from torchview import draw_graph
model_graph = draw_graph(LSTMn, input_size=(113, 14, 3), expand_nested=True)
model_graph.visual_graph
model_graph = draw_graph(ODENet, input_size=(113, 14, 3), expand_nested=True)
model_graph.visual_graph

colors = [["#87cefa","#3cb371","#ffd700"],["#00bfff","#228b22","#ffa500"],["#6495ed","#008000","#f4a460"],["#1e90ff","#006400","#ff8c00"]]

fig2 = go.Figure()

fig2 = make_subplots(rows=4, cols=1)

x_hum2 = predictions["LSTM"]["humidity"].index
y_hum2 = predictions["LSTM"]["humidity"]["humidity1"]
x_hum_p2 = predictions["LSTM"]["humidity"].index
y_hum_p2 = predictions["LSTM"]["humidity"]["prediction"]
x_wind2 = predictions["LSTM"]["wind_speed"].index
y_wind2 = predictions["LSTM"]["wind_speed"]["wind_speed1"]
x_wind_p2 = predictions["LSTM"]["wind_speed"].index
y_wind_p2 = predictions["LSTM"]["wind_speed"]["prediction"]
x_pres2 = predictions["LSTM"]["meanpressure"].index
y_pres2 = predictions["LSTM"]["meanpressure"]["meanpressure1"]
x_pres_p2 = predictions["LSTM"]["meanpressure"].index
y_pres_p2 = predictions["LSTM"]["meanpressure"]["prediction"]
x_temp2 = predictions["LSTM"]["meantemp"].index
y_temp2 = predictions["LSTM"]["meantemp"]["meantemp1"]
x_temp_p2 = predictions["LSTM"]["meantemp"].index
y_temp_p2 = predictions["LSTM"]["meantemp"]["prediction"]

x_hum3 = predictions["ODENET"]["humidity"].index
y_hum3 = predictions["ODENET"]["humidity"]["humidity1"]
x_hum_p3 = predictions["ODENET"]["humidity"].index
y_hum_p3 = predictions["ODENET"]["humidity"]["prediction"]
x_wind3 = predictions["ODENET"]["wind_speed"].index
y_wind3 = predictions["ODENET"]["wind_speed"]["wind_speed1"]
x_wind_p3 = predictions["ODENET"]["wind_speed"].index
y_wind_p3 = predictions["ODENET"]["wind_speed"]["prediction"]
x_pres3 = predictions["ODENET"]["meanpressure"].index
y_pres3 = predictions["ODENET"]["meanpressure"]["meanpressure1"]
x_pres_p3 = predictions["ODENET"]["meanpressure"].index
y_pres_p3 = predictions["ODENET"]["meanpressure"]["prediction"]
x_temp3 = predictions["ODENET"]["meantemp"].index
y_temp3 = predictions["ODENET"]["meantemp"]["meantemp1"]
x_temp_p3 = predictions["ODENET"]["meantemp"].index
y_temp_p3 = predictions["ODENET"]["meantemp"]["prediction"]

#["humidity", "wind_speed", "meanpressure", "meantemp"]

fig2.add_trace(go.Scatter(
    line=dict(color="#f20089"),
    x=x_hum2, y=y_hum2,
    mode='lines',
    name='Истинная влажность'), row = 1, col = 1)
fig2.add_trace(go.Scatter(
    line=dict(color="#e500a4"),
    x=x_wind2, y=y_wind2,
    mode='lines',
    name='Истинная скорость ветра'), row = 2, col = 1)
fig2.add_trace(go.Scatter(
    line=dict(color="#db00b6"),
    x=x_pres2, y=y_pres2,
    mode='lines',
    name='Истинное среднее давление'), row = 3, col = 1)
fig2.add_trace(go.Scatter(
    line=dict(color="#d100d1"),
    x=x_temp2, y=y_temp2,
    mode='lines',
    name='Истинная средняя температура'), row = 4, col = 1)

fig2.add_trace(go.Scatter(
    line=dict(color="#ffba08"),
    x=x_hum_p2, y=y_hum_p2,
    mode='lines',
    name='LSTM Предсказанная влажность'), row = 1, col = 1)

fig2.add_trace(go.Scatter(
    line=dict(color="#faa307"),
    x=x_wind_p2, y=y_wind_p2,
    mode='lines',
    name='LSTM Предсказанная скорость ветра'), row = 2, col = 1)

fig2.add_trace(go.Scatter(
    line=dict(color="#f48c06"),
    x=x_pres_p2, y=y_pres_p2,
    mode='lines',
    name='LSTM Предсказанное среднее давление'), row = 3, col = 1)

fig2.add_trace(go.Scatter(
    line=dict(color="#e85d04"),
    x=x_temp_p2, y=y_temp_p2,
    mode='lines',
    name='LSTM Предсказанная средняя температура'), row = 4, col = 1)


fig2.add_trace(go.Scatter(
    line=dict(color="#9ef01a"),
    x=x_hum_p3, y=y_hum_p3,
    mode='lines',
    name='ODENET Предсказанная влажность'), row = 1, col = 1)

fig2.add_trace(go.Scatter(
    line=dict(color="#70e000"),
    x=x_wind_p3, y=y_wind_p3,
    mode='lines',
    name='ODENET Предсказанная скорость ветра'), row = 2, col = 1)

fig2.add_trace(go.Scatter(
    line=dict(color="#38b000"),
    x=x_pres_p3, y=y_pres_p3,
    mode='lines',
    name='ODENET Предсказанное среднее давление'), row = 3, col = 1)

fig2.add_trace(go.Scatter(
    line=dict(color="#008000"),
    x=x_temp_p3, y=y_temp_p3,
    mode='lines',
    name='ODENET Предсказанная средняя температура'), row = 4, col = 1)

fig2.add_trace(go.Scatter(
    line=dict(color="#caf0f8"),
    x=hum_concated.index, y=hum_concated,
    mode='lines',
    name='SARIMA Предсказанная влажность'), row = 1, col = 1)


fig2.add_trace(go.Scatter(
    line=dict(color="#90e0ef"),
    x=wind_concated.index, y=wind_concated,
    mode='lines',
    name='SARIMA Предсказанная скорость ветра'), row = 2, col = 1)


fig2.add_trace(go.Scatter(
    line=dict(color="#00b4d8"),
    x=pres_concated.index, y=pres_concated,
    mode='lines',
    name='SARIMA Предсказанное среднее давление'), row = 3, col = 1)


fig2.add_trace(go.Scatter(
    line=dict(color="#0077b6"),
    x=temp_concated.index, y=temp_concated,
    mode='lines',
    name='SARIMA Предсказанная средняя температура'), row = 4, col = 1)

fig2.update_xaxes(title_text='Время', row=1, col=1)
fig2.update_yaxes(title_text='Влажность, %', row=1, col=1)

fig2.update_xaxes(title_text='Время', row=2, col=1)
fig2.update_yaxes(title_text='Скорость ветра, м/с', row=2, col=1)

fig2.update_xaxes(title_text='Время', row=3, col=1)
fig2.update_yaxes(title_text='Давление, мбар', row=3, col=1)

fig2.update_xaxes(title_text='Время', row=4, col=1)
fig2.update_yaxes(title_text='Температура, цельсий', row=4, col=1)

fig2.update_layout(height=800)


fig2.add_vline(x=test_start, line_width=2, line_dash="dash")
fig2.add_annotation(x=test_start, y=10, text="Начало теста", showarrow=False)

fig2.show()

#"humidity", "wind_speed", "meanpressure", "meantemp"
print(f"MSE влажность SARIMA: ", mean_absolute_error(predictions[mdl["name"]]["humidity"]["humidity1"]["2016-01-01":], sarimax_pred_hum))
print(f"MSE скорость ветра SARIMA: ", mean_absolute_error(predictions[mdl["name"]]["wind_speed"]["wind_speed1"]["2016-01-01":], sarimax_pred_wind))
print(f"MSE среднее давление SARIMA: ", mean_absolute_error(predictions[mdl["name"]]["meanpressure"]["meanpressure1"]["2016-01-01":], sarimax_pred_pres))
print(f"MSE средняя температура SARIMA: ", mean_absolute_error(predictions[mdl["name"]]["meantemp"]["meantemp1"]["2016-01-01":], sarimax_pred_temp))
print("SARIMA MEMORY")

print("SARIMA влажность память", asizeof.asizeof(sarimax_res_hum))
print("SARIMA ветер память", asizeof.asizeof(sarimax_res_wind))
print("SARIMA давление память", asizeof.asizeof(sarimax_res_pres))
print("SARIMA температура память", asizeof.asizeof(sarimax_res_temp))

for mdl in models:
    print(f"MSE влажность {mdl['name']}: ", mean_absolute_error(predictions[mdl["name"]]["humidity"]["humidity1"]["2016-01-01":], predictions[mdl["name"]]["humidity"]["prediction"]["2016-01-01":]))
    print(f"MSE скорость ветра {mdl['name']}: ", mean_absolute_error(predictions[mdl["name"]]["wind_speed"]["wind_speed1"]["2016-01-01":], predictions[mdl["name"]]["wind_speed"]["prediction"]["2016-01-01":]))
    print(f"MSE среднее давление {mdl['name']}: ", mean_absolute_error(predictions[mdl["name"]]["meanpressure"]["meanpressure1"]["2016-01-01":], predictions[mdl["name"]]["meanpressure"]["prediction"]["2016-01-01":]))
    print(f"MSE средняя температура {mdl['name']}: ", mean_absolute_error(predictions[mdl["name"]]["meantemp"]["meantemp1"]["2016-01-01":], predictions[mdl["name"]]["meantemp"]["prediction"]["2016-01-01":]))

    print(f"Время тренировки влажность {mdl['name']}: ", mdl["hwpt_train"])
    print(f"Время тренировки скорость ветра {mdl['name']}: ", mdl["hwpt_train"])
    print(f"Время тренировки среднее давление {mdl['name']}: ", mdl["hwpt_train"])
    print(f"Время тренировки средняя температура {mdl['name']}: ", mdl["hwpt_train"])

    print(f"Время теста влажность {mdl['name']}: ", mdl["hwpt_test"])
    print(f"Время теста скорость ветра {mdl['name']}: ", mdl["hwpt_test"])
    print(f"Время теста среднее давление {mdl['name']}: ", mdl["hwpt_test"])
    print(f"Время теста средняя температура {mdl['name']}: ", mdl["hwpt_test"])
    print("\n")

for mdl in models:
    print(str(mdl))
    print(f"Число параметров {mdl['params']}")
    print(f"Используемая память {mdl['memory']}")
    print(f"Используемая память asizeof {mdl['other_memory']}")
    print("\n")
