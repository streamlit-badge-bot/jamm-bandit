import numpy as np
import os
import urllib
from datetime import datetime

import torch
import stylegan2
from stylegan2 import utils

import streamlit as st
from streamlit.report_thread import get_report_ctx
from streamlit.server.server import Server
from streamlit.hashing import _CodeHasher

from pymongo import MongoClient

from logistic_regression import random_weights

def main():

    # session state for persistent values
    state = _get_state()

    # Set up database connection
    client = get_database_connection()  
    results = client.results


    now = datetime.now()
    user = results[get_unique_user_id()]

    st.title('Is this face warm?')

    # Download the model file
    download_file('Gs.pth')

    # Load the StyleGAN2 Model
    G = load_model()
    G.eval()

    # Feature Sliders 
    st.sidebar.title('Please fill this out before starting!')
    st.sidebar.number_input('Age', min_value=12, max_value=100)
    st.sidebar.selectbox('Gender', ('Male', 'Female', 'Other'))
    st.sidebar.selectbox('Ethnicity', ('White', 'Hispanic', 'Black', 'Middle Eastern', 'South Asian', 'South-East Asian', 'East Asian', 'Pacific Islander', 'Native American/Indigenous'))
    st.sidebar.selectbox('Political Orientation', ('Very Liberal', 'Moderately Liberal', 'Slightly Liberal', 'Neither Liberal or Conservative', 'Very Conservative', 'Moderately Conservative', 'Slightly Conservative'))
    st.sidebar.button('Submit')
    #default_control_features = ['Male']

    # Update the weights
    #rnd = np.random.RandomState(6600)
    #latents = rnd.randn(512)
    weights = random_weights()
    weights_str = np.array_str(weights, precision = 6, suppress_small = True)

    # Generate the image
    image_out = generate_image(G, weights)

    # Output the image
    st.image(image_out, use_column_width=True)
    

    if st.button('Yes'):
        new_result = {
            'reward': "yes",
            'latents': weights_str
        }
        user.insert_one(new_result)

    if st.button('No'):
        new_result = {
            'reward': "no",
            'latents': weights_str
        }
        user.insert_one(new_result)

    if st.button('There is something wrong with this picture!'):
        pass

    # Mandatory to avoid rollbacks with widgets, must be called at the end of your app
    state.sync()

@st.cache
def get_unique_user_id():
    now = datetime.now()
    return now.strftime("%m/%d/%Y, %H:%M:%S")

@st.cache(allow_output_mutation=True)
def get_database_connection():
    return MongoClient("mongodb+srv://jammadmin:jamm2020@cluster0.qch9t.mongodb.net/jamm?retryWrites=true&w=majority")

# @st.cache(hash_funcs={DBConnection: id})
# def get_users(connection):
#     # Note: We assume that connection is of type DBConnection.
#     return connection.execute_sql('SELECT * from Users')

@st.cache(show_spinner=False)
def generate_image(G, weights):
    latent_size, label_size = G.latent_size, G.label_size

    device = torch.device('cpu')
    if device.index is not None:
        torch.cuda.set_device(device.index)
    G.to(device)

    G.set_truncation(0.5)
    noise_reference = G.static_noise()
    noise_tensors = [[] for _ in noise_reference]

    latents = []
    labels = []
    rnd = np.random.RandomState(6600)
    latents.append(torch.from_numpy(weights))
            
    for i, ref in enumerate(noise_reference):
        noise_tensors[i].append(torch.from_numpy(rnd.randn(*ref.size()[1:])))

    if label_size:
        labels.append(torch.tensor([rnd.randint(0, label_size)]))
    
    latents = torch.stack(latents, dim=0).to(device=device, dtype=torch.float32)
    if labels:
        labels = torch.cat(labels, dim=0).to(device=device, dtype=torch.int64)
    else:
        labels = None
    
    noise_tensors = [torch.stack(noise, dim=0).to(device=device, dtype=torch.float32) for noise in noise_tensors]

    if noise_tensors is not None:
        G.static_noise(noise_tensors=noise_tensors)
    with torch.no_grad():
        generated = G(latents, labels=labels)
    
    images = utils.tensor_to_PIL(
        generated, pixel_min=-1, pixel_max=1)
    
    for img in images:
        #img.save('static/images/seed6600.png')
        return img

@st.cache(allow_output_mutation=True)
def load_model():
    return stylegan2.models.load('Gs.pth')
    
@st.cache
def download_file(file_path):
    # Don't download the file twice. (If possible, verify the download using the file length.)
    if os.path.exists(file_path):
        return

    # These are handles to two visual elements to animate.
    weights_warning, progress_bar = None, None
    try:
        weights_warning = st.warning("Downloading %s..." % file_path)
        progress_bar = st.progress(0)
        with open(file_path, "wb") as output_file:
            with urllib.request.urlopen("https://d1p4vo8bv9dco3.cloudfront.net/Gs.pth") as response:
                length = int(response.info()["Content-Length"])
                counter = 0.0
                MEGABYTES = 2.0 ** 20.0
                while True:
                    data = response.read(8192)
                    if not data:
                        break
                    counter += len(data)
                    output_file.write(data)

                    # We perform animation by overwriting the elements.
                    weights_warning.warning("Downloading %s... (%6.2f/%6.2f MB)" %
                        (file_path, counter / MEGABYTES, length / MEGABYTES))
                    progress_bar.progress(min(counter / length, 1.0))

    # Finally, we remove these visual elements by calling .empty().
    finally:
        if weights_warning is not None:
            weights_warning.empty()
        if progress_bar is not None:
            progress_bar.empty()


class _SessionState:

    def __init__(self, session, hash_funcs):
        """Initialize SessionState instance."""
        self.__dict__["_state"] = {
            "data": {},
            "hash": None,
            "hasher": _CodeHasher(hash_funcs),
            "is_rerun": False,
            "session": session,
        }

    def __call__(self, **kwargs):
        """Initialize state data once."""
        for item, value in kwargs.items():
            if item not in self._state["data"]:
                self._state["data"][item] = value

    def __getitem__(self, item):
        """Return a saved state value, None if item is undefined."""
        return self._state["data"].get(item, None)
        
    def __getattr__(self, item):
        """Return a saved state value, None if item is undefined."""
        return self._state["data"].get(item, None)

    def __setitem__(self, item, value):
        """Set state value."""
        self._state["data"][item] = value

    def __setattr__(self, item, value):
        """Set state value."""
        self._state["data"][item] = value
    
    def clear(self):
        """Clear session state and request a rerun."""
        self._state["data"].clear()
        self._state["session"].request_rerun()
    
    def sync(self):
        """Rerun the app with all state values up to date from the beginning to fix rollbacks."""

        # Ensure to rerun only once to avoid infinite loops
        # caused by a constantly changing state value at each run.
        #
        # Example: state.value += 1
        if self._state["is_rerun"]:
            self._state["is_rerun"] = False
        
        elif self._state["hash"] is not None:
            if self._state["hash"] != self._state["hasher"].to_bytes(self._state["data"], None):
                self._state["is_rerun"] = True
                self._state["session"].request_rerun()

        self._state["hash"] = self._state["hasher"].to_bytes(self._state["data"], None)


def _get_session():
    session_id = get_report_ctx().session_id
    session_info = Server.get_current()._get_session_info(session_id)

    if session_info is None:
        raise RuntimeError("Couldn't get your Streamlit Session object.")
    
    return session_info.session


def _get_state(hash_funcs=None):
    session = _get_session()

    if not hasattr(session, "_custom_session_state"):
        session._custom_session_state = _SessionState(session, hash_funcs)

    return session._custom_session_state

if __name__ == "__main__":
    main()