import os
import torch
import numpy as np
from torch.utils.tensorboard import SummaryWriter
from datetime import datetime

def initialize_environment(args):
    base_dir = f'./results/{args.name}'
    snapshot_dir = os.path.join(base_dir, 'snapshots')
    output_dir = os.path.join(base_dir, 'outputs')
    log_dir = os.path.join(base_dir, 'logs')
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(snapshot_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    return base_dir, snapshot_dir, output_dir, log_dir

class Logger:
    def __init__(self, args, base_dir, snapshot_dir, output_dir, log_dir, level_num=11, only_print=False):
        self.args = args
        self.base_dir = base_dir
        self.snapshot_dir = snapshot_dir
        self.output_dir = output_dir
        self.log_dir = log_dir
        self.level_num = level_num
        self.itr = 0
        self.init()

        if not only_print:
            self._init_summary_writers(level_num)

    def _init_summary_writers(self, level_num):
        self.writer = SummaryWriter(self.log_dir)

    def init(self):
        self.loss = AverageMeter()
        self.loss_nll = AverageMeter()
        self.loss_reg = AverageMeter()
        self.loss_unc = AverageMeter()
        self.mse = AverageMeter()
        # self.test_mse = AverageMeter()
        # self.test_nll = AverageMeter()
        # self.test_reg = AverageMeter()


    def load_itr(self, itr):
        self.itr = itr

    def update(self, out_criterion):
        self.loss.update(out_criterion['loss'])
        if 'loss_nll' in out_criterion.keys():
            self.loss_nll.update(out_criterion['loss_nll'])
        if 'loss_reg' in out_criterion.keys():
            self.loss_reg.update(out_criterion['loss_reg'])
        if 'loss_unc' in out_criterion.keys():
            self.loss_unc.update(out_criterion['loss_unc'])
        if 'mse' in out_criterion.keys():
            self.mse.update(out_criterion['mse'])
        # if 'test_mse' in out_criterion.keys():
        #     self.test_mse.update(out_criterion['test_mse'])
        # if 'test_nll' in out_criterion.keys():
        #     self.test_nll.update(out_criterion['test nll'])
        # if 'test_reg' in out_criterion.keys():
        #     self.test_reg.update(out_criterion['test_reg'])
        
        self.itr += 1

    def print(self):
        print(
            f'[{self.itr:>6}]'
            f' loss_nll:          {self.loss_nll.avg:.4f} |'
            f' loss_reg:          {self.loss_reg.avg:.4f} |'
            f' loss_unc:          {self.loss_unc.avg:.4f} |'
            f' loss:              {self.loss.avg:.4f} |'
            f' mse:               {self.mse.avg:.4f} |'
            # f' test_mse:          {self.test_mse.avg:.4f} |'
            # f' test_nll:          {self.test_nll.avg:.4f} |'
            # f' test_reg:          {self.test_reg.avg:.4f} |'
        )

    def write(self):
        self.writer.add_scalar('Total loss', self.loss.avg, self.itr)
        self.writer.add_scalar('NLL loss', self.loss_nll.avg, self.itr)
        self.writer.add_scalar('Reg loss', self.loss_reg.avg, self.itr)
        self.writer.add_scalar('Unc loss', self.loss_unc.avg, self.itr)
        self.writer.add_scalar('MSE', self.mse.avg, self.itr)
        # self.writer.add_scalar('Test MSE', self.test_mse.avg, self.itr)
        # self.writer.add_scalar('Test NLL', self.test_nll.avg, self.itr)
        # self.writer.add_scalar('Test Reg', self.test_reg.avg, self.itr)

    
    def model(self, model, input):
        model_log_path = os.path.join(self.log_dir, self.args.aetype)
        writer =  SummaryWriter(model_log_path)
        writer.add_graph(model, input)


class AverageMeter:
    """Compute running average."""
    def __init__(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count

def count_params(model, verbose=True):
    """
    Counts and returns the total number of parameters in a model.

    Args:
        model (torch.nn.Module): The model to count parameters for.
        verbose (bool, optional): If True, print the total number of parameters in millions. 

    Returns:
        int: Total number of parameters in the model.
    """
    total_params = sum(p.numel() for p in model.parameters())
    if verbose:
        print(f"{model.__class__.__name__} has {total_params * 1.e-6:.2f} M params.")
    return total_params

def save_checkpoint(filename, itr, model):
    snapshot = {
        'itr': itr,
        'model': model.state_dict(),
        # 'optimizer': optimizer.state_dict(),
    }
    torch.save(snapshot, filename)
    # torch.save(model.state_dict(), filename)

def load_checkpoint(path, model, device='gpu'):
    snapshot = torch.load(path, map_location=device, weights_only=True)

    # snapshot = torch.load(path, map_location=device)
    itr = snapshot['itr']
    print(f'Loaded from {itr} iterations')
    model.load_state_dict(snapshot['model'])
    return itr, model

def is_bool_tensor(tensor):
    """
    Checks if the given tensor is a boolean tensor in PyTorch.
    
    Returns:
        bool: True if `tensor` is a boolean tensor, False otherwise.
    """
    return isinstance(tensor, torch.Tensor) and tensor.dtype == torch.bool


def get_duration(start, end):
    """
    Calculate the duration between two datetime objects and return the time in hours, minutes, and seconds.
    
    Parameters:
    - start (datetime): The start time.
    - end (datetime): The end time.
    
    Returns:
    - tuple: A tuple containing the duration in hours, minutes, and seconds (h, m, s).
    
    Raises:
    - ValueError: If end time is before start time.
    """
    
    if end < start:
        raise ValueError("end time must not be before start time")
    
    # Calculate total duration in seconds
    h, remainder = divmod((end - start).seconds, 3600)
    m, s = divmod(remainder, 60)
    
    return h, m, s


def PSNR_MSE(x, y, max=255, istorch=False, mask=None):
    if istorch:
        if mask is not None:
            mse = torch.mean((x - y) ** 2, dim=[1, 2, 3, 4])
            mse = mse * ~mask.to(torch.bool)
        else:
            mse = torch.mean((x - y) ** 2, dim=[1, 2, 3, 4])
        psnr = 10 * torch.log10(max ** 2. / mse)
    else:
        if mask is not None:
            mse = np.mean(((x - y) ** 2)* ~np.array(mask, dtype=bool))
        else:
            mse = np.mean((x - y) ** 2)
        psnr = 20 * np.log10(max / np.sqrt(mse))
    return psnr, mse

def MSE(x, y, istorch=False):
    if istorch:
        mse = torch.mean((x - y) ** 2, dim=[1])
    else:
        mse = np.mean((x - y) ** 2)
    return mse

class EMA:
    """
    A class that implements the Exponential Moving Average (EMA) for model parameters.
    EMA helps in stabilizing the model training by smoothing the parameters over time,
    which can lead to improved performance on validation and test sets and reduced overfitting.

    Attributes:
        beta (float): The decay factor that controls the rate at which older observations
                      are decayed. A higher beta values less responsiveness to recent changes.
        step (int): A counter for the number of updates, used to manage when the EMA updates start (1/(1-beta)).
    """
    def __init__(self, beta=0.9998):
        """
        Initializes the EMA object with the specified beta decay factor.

        Parameters:
            beta (float): The decay factor for the exponential moving average.
        """
        super().__init__()
        self.beta = beta
        self.step = 0

    def update_model_average(self, ma_model, current_model):
        """
        Updates the moving average model's parameters based on the parameters from the current model.

        Parameters:
            ma_model (torch.nn.Module): The moving average model whose parameters are to be updated.
            current_model (torch.nn.Module): The current model providing the latest parameters.
        """
        for current_params, ma_params in zip(current_model.parameters(), ma_model.parameters()):
            old_weight, up_weight = ma_params.data, current_params.data
            ma_params.data = self.update_average(old_weight, up_weight)

    def update_average(self, old, new):
        """
        Computes the new average based on the old value and the new value using the EMA formula.

        Parameters:
            old (torch.Tensor): The old parameter value.
            new (torch.Tensor): The new parameter value from the current model.

        Returns:
            torch.Tensor: The updated parameter value based on EMA.
        """
        if old is None:
            return new
        return old * self.beta + (1 - self.beta) * new

    def step_ema(self, ema_model, model, step_start_ema=2000):
        """
        Controls the updating process of the EMA parameters based on the step count.

        Parameters:
            ema_model (torch.nn.Module): The EMA model to update.
            model (torch.nn.Module): The current training model.
            step_start_ema (int): The number of steps to delay before starting EMA updates.
        """
        if self.step < step_start_ema:
            self.reset_parameters(ema_model, model)
            self.step += 1
            return
        self.update_model_average(ema_model, model)
        self.step += 1

    def reset_parameters(self, ema_model, model):
        """
        Resets the EMA model's parameters to the current model's parameters. This is usually done
        before the EMA updates begin.

        Parameters:
            ema_model (torch.nn.Module): The EMA model whose parameters are reset.
            model (torch.nn.Module): The current model from which to copy the parameters.
        """
        ema_model.load_state_dict(model.state_dict())
