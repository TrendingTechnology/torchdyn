import torch
import torch.nn as nn
import numpy as np

def FourierExpansion(n_range, s):
    """Fourier eigenbasis expansion
    """
    s_n_range = 2*np.pi*s*n_range
    basis = [torch.cos(s_n_range), torch.sin(s_n_range)]
    return basis
  
def PolyExpansion(n_range, s):
    """Polynomial expansion
    """
    basis = [s**n_range]
    return basis

# can be slimmed down with template class (sharing assign_weights and reset_parameters) 
class GalLinear(nn.Module):
    """Linear Galerkin layer for depth--variant neural differential equations

    :param in_features: input dimensions
    :type in_features: int
    :param out_features: output dimensions
    :type out_features: int
    :param expfunc: {'FourierExpansion', 'PolyExpansion'}. Choice of eigenfunction expansion.
    :type expfunc: str
    :param n_harmonics: number of elements of the truncated eigenfunction expansion.
    :type n_harmonics: int
    :param n_eig: number of distinct eigenfunctions in the basis
    :type n_eig: int
    :param bias: include bias parameter vector in the layer computation
    :type bias: bool
    """
    def __init__(self, in_features, out_features, expfunc=FourierExpansion, n_harmonics=10, n_eig=2, bias=True):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.expfunc = expfunc
        self.n_eig = n_eig
        self.n_harmonics = n_harmonics
        self.weight = torch.Tensor(out_features, in_features)
        if bias:
            self.bias = torch.Tensor(out_features)
        else:
            self.register_parameter('bias', None)         
        self.coeffs = torch.nn.Parameter(torch.Tensor((in_features+1)*out_features, n_harmonics, n_eig))        
        self.reset_parameters()  
        
    def reset_parameters(self):
        torch.nn.init.zeros_(self.coeffs)
        
    def assign_weights(self, s):
        n_range = torch.linspace(0, self.n_harmonics, self.n_harmonics).to(self.coeffs.device)
        basis = self.expfunc(n_range, s)
        B = []  
        for i in range(self.n_eig):
            Bin = torch.eye(self.n_harmonics).to(self.coeffs.device)
            Bin[range(self.n_harmonics), range(self.n_harmonics)] = basis[i]
            B.append(Bin)
        B = torch.cat(B, 1).to(self.coeffs.device)
        coeffs = torch.cat([self.coeffs[:,:,i] for i in range(self.n_eig)],1).transpose(0,1).to(self.coeffs.device) 
        X = torch.matmul(B, coeffs)
        return X.sum(0)
      
    def forward(self, input):
        s = input[-1,-1]
        input = input[:,:-1]
        w = self.assign_weights(s)
        self.weight = w[0:self.in_features*self.out_features].reshape(self.out_features, self.in_features)
        self.bias = w[self.in_features*self.out_features:(self.in_features+1)*self.out_features].reshape(self.out_features)
        return torch.nn.functional.linear(input, self.weight, self.bias)
    
class GalConv2d(nn.Module):
    """2D convolutional Galerkin layer for depth--variant neural differential equations

    :param in_channels: number of channels in the input image
    :type in_channels: int
    :param out_channels: number of channels produced by the convolution
    :type out_channels: int
    :param kernel_size: size of the convolving kernel
    :type kernel_size: int
    :param stride: stride of the convolution. Default: 1
    :type stride: int
    :param padding: zero-padding added to both sides of the input. Default: 0
    :type padding: int
    :param expfunc: {'FourierExpansion', 'PolyExpansion'}. Choice of eigenfunction expansion.
    :type expfunc: str
    :param n_harmonics: number of elements of the truncated eigenfunction expansion.
    :type n_harmonics: int
    :param n_eig: number of distinct eigenfunctions in the basis
    :type n_eig: int
    :param bias: include bias parameter vector in the layer computation
    :type bias: bool
    """
    __constants__ = ['bias', 'in_channels', 'out_channels', 'kernel_size', 'stride', 'padding', 'n_harmonics']

    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=0, 
                 expfunc=FourierExpansion, n_harmonics=10, n_eig=2, bias=True):
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.pad = padding
        self.stride = stride
        self.expfunc = expfunc
        self.n_eig = n_eig
        self.n_harmonics = n_harmonics
        self.weight = torch.Tensor(out_channels, in_channels, kernel_size, kernel_size)
        if bias:
            self.bias = torch.Tensor(out_channels)
        else:
            self.register_parameter('bias', None)

        self.coeffs = torch.nn.Parameter(torch.Tensor(((out_channels)*in_channels*(kernel_size**2)+out_channels), n_harmonics, 2))

        self.reset_parameters()
        self.ic, self.oc, self.ks, self.nh = in_channels, out_channels, kernel_size, n_harmonics

    def reset_parameters(self):
        torch.nn.init.zeros_(self.coeffs)
        
    def assign_weights(self, s):
        n_range = torch.linspace(0, self.n_harmonics, self.n_harmonics).to(self.coeffs.device)
        basis = self.expfunc(n_range, s)
        B = []  
        for i in range(self.n_eig):
            Bin = torch.eye(self.n_harmonics).to(self.coeffs.device)
            Bin[range(self.n_harmonics), range(self.n_harmonics)] = basis[i]
            B.append(Bin)
        B = torch.cat(B, 1).to(self.coeffs.device)
        coeffs = torch.cat([self.coeffs[:,:,i] for i in range(self.n_eig)],1).transpose(0,1).to(self.coeffs.device) 
        X = torch.matmul(B, coeffs)
        return X.sum(0)

    def forward(self, input):
        s = input[-1,-1,0,0]
        input = input[:,:-1]
        w = self.assign_weights(s)
        n = self.oc*self.ic*self.ks*self.ks
        self.weight = w[0:n].reshape(self.oc, self.ic, self.ks, self.ks)
        self.bias = w[n:].reshape(self.oc)
        return torch.nn.functional.conv2d(input, self.weight, self.bias, stride=self.stride, padding=self.pad)