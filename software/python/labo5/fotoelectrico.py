import matplotlib.pyplot as plt
import scipy.optimize as opt
from instrumentos import Lockin
import numpy as np
import time
import os
import glob

# Configuracion. Se puede cambiar sobre la marcha
config = {
          'medicion_path' : r'PATH_MED',
          'espectro_path' :  r'PATH_ESPECTRO',
          'lockin_addr': 'GPIB0::1::INSTR',
          #Página 90 del manual del Lockin SR830
          'v_sens' : 24, 
          't_slope' : 3, #18dB/oct
          't_base' : 7, #Tiempo de integración 300ms
          'aux_out' : 1,
          'aux_v_min' : -3,
          'aux_v_max' : 0.5,
          'ref_intern' : False,
          'ref_freq' : 500, 
          'ref_v' : 5,
          'medicion_dt': 25, #Múltiplo del tiempo de integración
          'medicion_modo' : 2,
          'medicion_xy' : True,
          }

# Funciones de manejo de Lockin:
def init(config):
    """Inicialización del Lockin. Devuelve la instancia lista para usar."""
    inst = Lockin(config['lockin_addr'])
    inst.set_referencia(isIntern = config['ref_intern'],
                        freq = config['ref_freq'],
                        v_ref = config['ref_v'])
    inst.set_modo(config['medicion_modo'])
    #Bloquea el uso de teclas del Lockin
    inst.write("LOCL 2")
    #Setea filtro del lockin
    inst.set_filtro(config['v_sens'], config['t_base'], config['t_slope'])
    ## Setea tensión de referencia ## 
    
    #Configura el display.
    inst.set_display(config['medicion_xy'])
    inst.set_aux_out(config['aux_out'], config['v_min'])
    time.sleep(5) #Está 5s antes de seguir
    return inst


def adquiere_corriente(config):
    """
    Adquirir datos del lockin para la expriencia. Varía la tensión de salida
    del Aux 1 entre la tensión vOut_min y vOut_max, y mide corriente. Se puede
    setear el tiempo de integración, el tiempo entre medición y medición
    que corresponde a un múltiplo del tiempo de integración,
    la sensibilidad, la frecuencia de referencia y la tensión de referencia.
    """
    file_name = config['medicion_path']
    v_min = config['aux_v_min']
    v_max = config['aux_v_max']
    #Calcula el tiempo para esperar
    t_wait = 0
    if config['t_base'] % 2 == 0:
        t_wait = 1 * 10**(config['t_base']/2-5)
    else:
        t_wait = 3 * 10**(-(config['t_base']-1)/2)
    t_wait *= config['medicion_dt']
    os.chdir()
    # Tensiones a medir
    # Con np.concatenate((a,b)) se puede hacer pasos variables
    tensiones = np.arange(v_min, v_max ,0.01)
    # Configuración inicial
    lockin = init(config)
    # Iteración sobre las tensiones
    data = []
    for v in tensiones(v_min, v_max):
        lockin.set_aux_out(aux_out=config['aux_out'], aux_v=v)
        #Calcula la base de tiempo a partir de la tabla
        # Espera un múltiplo del tiempo de base
        time.sleep(t_wait)
        #Medición
        med = lockin.get_display() #o lockin.get_medicion(config['medicion_xy'])
        med.insert(0,v) #Agrega la tensión de aux
        data.append(med)
    data = np.array(data) #Transformo en ndarray
    np.savetxt(file_name, data)

    # Herramienta de ploteo de verificación
    plt.plot(data[:,0],data[:,1],'bo-')
    plt.figure()
    plt.plot(data[:,0],data[:,2],'gd-')
    plt.show()


def fit_corrientes(espectro_path, data_path):
    '''
    Ajuste de la fotocorriente, sabiendo el espectro de la fuente luminica
    usada. Necesita el path a un archivo doble columna que representa el 
    espectro y el path al archivo de datos, de doble o más columna, donde
    la primer columna es la tensión de frenado y la segunda la corriente
    '''
    data = np.loadtxt(data_path)
    spectrum = np.loadtxt(espectro_path)
    #freq = c/spectrum[:,0]
    #v = np.linspace(-0.5,0.5,1000) #Dominio para las funciones
    #print(weight.shape)

    def fitfun(espectro):
        a = espectro[:, 1] / np.max(espectro[:, 1])
        lambdas = espectro[:, 0]
        def _aux(v, offset, m, c, phi):
            #aux = sum_i A_i * m * (v - V0) + offset
            suma = np.zeros_like(v)
            for i, lambd in enumerate(lambdas):
                #Potencial de frenado, acá aparece la relación entre 
                #los parámetros que va a ajustar
                v0 = c / lambd - phi
                delta_v = v - v0
                sel = delta_v > 0 #Tensiones mayores a V0. Devuelve indices
                suma[sel] += a[i] * m * delta_v[sel]
            return suma + offset
        return _aux
    c = 1.238e3
    f = lambda v, offset, m, phi: fitfun(spectrum)(v, offset, m, c, phi)

    a, b = 5, -20 # Elimino al principio y al final elementos del ajuste
    v = np.linspace(np.min(data[a:b,0]),np.max(data[a:b,0]),1000)
    
    beta0 = (0, 1e-10, 2 )
    p, pconv = opt.curve_fit(f,data[a:b,0],data[a:b,1], p0 = beta0)
    plt.figure()
    plt.plot(data[a:b,0],data[a:b,1],'bo-',markersize=2)
    plt.plot(v, f(v, *p), 'r-', linewidth = 2)
    # Test de sensibilidad de chi-cuadrado
    x = np.linspace(.5,1.5,20)
    y = np.linspace(.5,1.5,20)
    chisqr = lambda f, x, y, *p : np.sum((f(x,*p) - y)**2)
    chisqr_param = np.vectorize(lambda x, y: chisqr(f, data[a:b,0] , data[a:b,1], p[0], p[1], x*p[2], y * p[3]))
    X, Y = np.meshgrid(x,y)
    plt.figure()
    plt.pcolor(X, Y, chisqr_param(X, Y)/np.min(chisqr_param(X, Y)))
    plt.show()
    print(p)


def plot_corrientes_norm(path_corrientes):
    """
    Plotea las fotocorrientes normalizadas encontradas en la dirección
    ingresada. Normalizar significa que la parte lineal tiene la misma pendiente
    y que V0 usando la parte lineal van a coincidir para todas
    """
    os.chdir(path_corrientes) # Accede a la carpeta donde están las corrientes
    corrientes = glob.glob("*_corriente.csv") # Obtiene todos los archivos con ese patrón
    corrientes.sort() # Los ordena alfabéticamente a los archivos
    labels = [c.replace("_corrientes.csv","").replace("_"," ") for c in corrientes]
    # Detalles cosméticos de los plots
    colors = ['red','blue','crimson','blue','blueviolet','violet']
    markers = ['-','-','-','-','-','-']
    _make_fig(r"Voltaje[v]", r"Corriente[A]")
    for i, c in enumerate(corrientes): # separo los datos
        data = np.loadtxt(c, delimiter = ' ')
        
        
        voltaje = data[2:-2,0] # Elimino algún dato espureo
        corriente = data[2:-2,1]
        # Puedo eliminar un offset en la corriente inicial
        #offset = np.mean(corriente[:10])
        #corriente -= offset
        #Cambiando theta puedo enfasar x e y, por si necesito usuarlo
        #theta = d[ind,2].copy() * np.pi / 180
        # Ajuste de la parte lineal
        fit_ind = np.logical_and(data[:,0] < 0.5, data[:,0] > -0.1)
        f = lambda x, a, b: a + b * x
        p, conv = opt.curve_fit(f, data[fit_ind,0], data[fit_ind,1])
        #Normalizado de la corriente y centrado de los V0 a uno sólo
        corriente /= p[1]
        voltaje += p[0]/p[1]
        #Redefino los datos a plotear
        plot_ind = np.logical_and(voltaje < 0.6, voltaje > -1)
        voltaje = voltaje[plot_ind]
        corriente = corriente[plot_ind]
        plt.plot(voltaje, corriente, markers[i],
                 markersize=7, label=labels[i], linewidth=3, color=colors[i])
    plt.legend(loc = 0)
    plt.show()
    
    
def plot_corrientes(path_corrientes):
    '''
    Plotea las fotocorrientes encontradas en la dirección
    ingresada.
    '''
    os.chdir(path_corrientes) #Accede a la carpeta donde están las corrientes
    corrientes = glob.glob("*_corriente.csv") #Obtiene todos los archivos con ese patrón
    corrientes.sort() #Los ordena alfabéticamente a los archivos
    labels = [c.replace("_corrientes.csv","").replace("_"," ") for c in corrientes]
    #Detalles cosméticos de los plots
    colors = ['red','blue','crimson','blue','blueviolet','violet']
    markers = ['-','-','-','-','-','-']
    _make_fig(r"Voltaje[v]", r"Corriente[A]")
    for i, c in enumerate(corrientes):#separo los datos
        data = np.loadtxt(c, delimiter = ' ')

        voltaje = data[2:-2,0] #Elimino algún dato espureo
        corriente = data[2:-2,1]
    
        #Cambiando theta puedo enfasar x e y, por si necesito usuarlo
        #theta = d[ind,2].copy() * np.pi / 180
        #Ajuste de la parte lineal
        fit_ind = np.logical_and(data[:,0] < 0.5, data[:,0] > -0.1)
        f = lambda x, a, b: a + b * x
        p, conv = opt.curve_fit(f, data[fit_ind,0], data[fit_ind,1])
        #Redefino los datos a plotear
        plot_ind = np.logical_and(voltaje < 0.6, voltaje > -1)
        voltaje = voltaje[plot_ind]
        corriente = corriente[plot_ind]
        plt.plot(voltaje, corriente, markers[i],
                 markersize=7, label=labels[i], linewidth = 3, color = colors[i]) 
    plt.legend(loc = 0)
    plt.show()


def plot_espectros(path_espectros):
    '''Plotea los espectros encontrados en la dirección ingresada'''
    os.chdir(path_espectros)
    espectros = glob.glob("*_spec.csv")
    espectros.sort()
    labels = [e.replace(".spec","").replace("_"," ") for e in espectros]
    _make_fig(r"$\lambda$[nm]", r"A[ua]")
    colors = ['blue','blueviolet','red','brown','green','limegreen']
    plt.xlim((350,800))
    plt.ylim((0,1.1))
    for i, e in enumerate(espectros):
        data = np.loadtxt(e)
        cero = np.mean(data[0:20,1])
        data[:,1] -= cero
        data[:,1] /= np.max(data[:,1])
        plt.plot(data[:,0],data[:,1],color = colors[i],
                 label=labels[i], linewidth = 2)
    plt.legend(loc=0)
    plt.show()
    
    
def sim_modelo():
    """Simulacion del modelo espectral propuesto
    """
    plt.figure()
    for k in (10,20,200):
     # creo gaussiana
     mu = 450.0
     std = k
     tam = 10000.0
     muestra = np.random.normal(mu, std, tam)
    
     # creo los bins
     minimo = round(np.min(muestra),1)
     if abs(minimo) < abs(np.min(muestra)):
         minimo = minimo-1
     maximo = round(np.max(muestra),1)
     if abs(maximo) < abs(np.max(muestra)):
         maximo  =maximo + 1
     num = ((maximo-minimo)/2)+1
     bins = np.linspace(minimo,maximo,num)
    
     #histograma
     histograma=[]
     for i in range(0, np.size(bins)-1):
         indice = 0
         for j in range(0, np.size(muestra)):
             if muestra[j] < bins[i+1] and muestra[j] >= bins[i]:
                 indice = indice + 1
         histograma.append(indice/tam)
     x=[]
     for i in range(1,np.size(histograma)+1):
         x.append(bins[i])
    
     #Fotoelectrico
    
     v = np.linspace(-1,2,1000)
     corriente = []
     for j in histograma:
        corriente=[]
        for i in v:
            V0=1.3*j
            if i<V0:
                corriente.append(0)
            else: 
                corriente.append(j*(i-V0))
        corriente.append(corriente)
     it=np.linspace(0,0,np.size(v))
     for j in range(0,np.size(histograma)):
        for i in range(0,np.size(v)):
            it[i]=it[i]+corriente[j][i]
     plt.axis([-0.005,0.08,-0.0005,0.01])
     plt.plot(v,it)
    plt.show()
    
def _make_fig(x_label, y_label):
    '''
    Función auxiliar para estadarizar el formato de los gráficos ploteados
    '''
    fig = plt.figure(figsize =(10, 10 * (np.sqrt(5) - 1)/2)) #En pulgadas
    plt.tick_params(labelsize= 15) #En puntos
    #plt.ticklabel_format(style = 'sci', scilimits = (-2,2),axis = 'y')
    plt.grid()
    plt.xlabel(x_label, fontsize=20)
    plt.ylabel(y_label, fontsize=20)
    return fig
