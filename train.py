import argparse
import time
import torch
import torch.nn as nn
import torch.nn.parallel
import torch.backends.cudnn as cudnn
import torch.optim
import loaddata
import numpy as np
import sobel
from models import modules, net, resnet, densenet, senet
import cv2
import os
from tensorboard_logger import configure, log_value
import tensorboard_logger as tb_logger

parser = argparse.ArgumentParser(description='PyTorch DenseNet Training')
parser.add_argument('--epochs', default=2, type=int,
                    help='number of total epochs to run')
parser.add_argument('--start_epoch', default=0, type=int,
                    help='manual epoch number (useful on restarts)')
parser.add_argument('--lr', '--learning-rate', default=0.0001, type=float,
                    help='initial learning rate')
parser.add_argument('--momentum', default=0.9, type=float, help='momentum')
parser.add_argument('--weight-decay', '--wd', default=1e-4, type=float,
                    help='weight decay (default: 1e-4)')
parser.add_argument('--data', default='/kaggle/input/osidataset/osiDataset')
parser.add_argument('--csv', default='/kaggle/working/IMELE_Copy/dataset/train.csv')
parser.add_argument('--model', default='/kaggle/working/IMELE_Copy/pretrained_model/encoder/senet154-c7b49a05.pth')
parser.add_argument('--save-interval', default=5, type=int,  # 每隔多少个Epoch保存一次Checkpoint
                    help='interval for saving checkpoints')
args = parser.parse_args()
# save_model = args.data+'/'+'_model_'
save_model = '/kaggle/working/IMELE_Copy'+'/'+'model_'

if not os.path.exists(args.data):
    os.makedirs(args.data)

def define_model(is_resnet, is_densenet, is_senet):
    if is_resnet:
        original_model = resnet.resnet50(pretrained = True)
        Encoder = modules.E_resnet(original_model) 
        model = net.model(Encoder, num_features=2048, block_channel = [256, 512, 1024, 2048])
    if is_densenet:
        original_model = densenet.densenet161(pretrained=True)
        Encoder = modules.E_densenet(original_model)
        model = net.model(Encoder, num_features=2208, block_channel = [192, 384, 1056, 2208])
    if is_senet:
        original_model = senet.senet154(pretrained='imagenet')
        Encoder = modules.E_senet(original_model)
        model = net.model(Encoder, num_features=2048, block_channel = [256, 512, 1024, 2048])
    return model

def main():
    global args
    args = parser.parse_args()
    model = define_model(is_resnet=False, is_densenet=False, is_senet=True)
    if args.start_epoch != 0:
        model = torch.nn.DataParallel(model, device_ids=[0]).cuda()
        model = model.cuda()
        state_dict = torch.load(args.model)['state_dict']
        model.load_state_dict(state_dict)
        batch_size = 2
    else:
        model = model.cuda()
        # model = torch.nn.DataParallel(model, device_ids=[0, 1]).cuda()
        batch_size = 2

    cudnn.benchmark = True
    #optimizer = torch.optim.SGD(model.parameters(), args.lr, weight_decay=args.weight_decay)
    optimizer = torch.optim.Adam(model.parameters(), args.lr, weight_decay=args.weight_decay)
    train_loader = loaddata.getTrainingData(batch_size,args.csv)
    logfolder = "runs/"
    if not os.path.exists(logfolder):
        os.makedirs(logfolder)
    # 判断默认日志记录器是否已经配置
    if not hasattr(tb_logger, "_default_logger"):
        tb_logger.configure(logfolder)
    for epoch in range(args.start_epoch, args.epochs):
        adjust_learning_rate(optimizer, epoch)
    # 到这为止
    for epoch in range(args.start_epoch, args.epochs):
        adjust_learning_rate(optimizer, epoch)
        train(train_loader, model, optimizer, epoch)
        #新的
        if (epoch + 1) % args.save_interval == 4 or epoch == args.epochs - 1:
            # 保存Checkpoint，每隔一定数量的Epoch保存一次，并且最后一个Epoch一定要保存
            out_name = save_model + f'epoch_{epoch}.pth.tar'
            modelname = save_checkpoint({'state_dict': model.state_dict()}, out_name)
            print(f"Saved checkpoint at epoch {epoch}: {modelname}")

        #旧的
        #out_name = save_model+str(epoch)+'.pth.tar'
        ## if epoch > 30:
        ## !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!保留Checkpoint的设置
        #modelname = save_checkpoint({'state_dict': model.state_dict()},out_name)
        #print(modelname)

def train(train_loader, model, optimizer, epoch):
    criterion = nn.L1Loss()
    batch_time = AverageMeter()
    losses = AverageMeter()
    model.train()
    cos = nn.CosineSimilarity(dim=1, eps=0)
    get_gradient = sobel.Sobel().cuda()
    global args
    args = parser.parse_args()
    end = time.time()
    for i, sample_batched in enumerate(train_loader):     
        image, depth = sample_batched['image'], sample_batched['depth']
        # depth = depth.cuda(async=True)
        # depth = depth.cuda(async_=True)
        depth = depth.cuda(non_blocking=True)
        image = image.cuda()
        image = torch.autograd.Variable(image)
        depth = torch.autograd.Variable(depth)
        ones = torch.ones(depth.size(0), 1, depth.size(2),depth.size(3)).float().cuda()
        ones = torch.autograd.Variable(ones)
        optimizer.zero_grad()
        output = model(image)
        # 尝试保存训练过程中的图片，修改了保存位置
        save_path = '/kaggle/working/'
        if i%200 == 0:
            x = output[0]
            x = x.view([220,220])
            x = x.cpu().detach().numpy()
            x = x*100000
            x2 = depth[0]
            print(x)
            x2 = x2.view([220,220])
            x2 = x2.cpu().detach().numpy()
            x2 = x2  *100000
            print(x2)
            x = x.astype('uint16')
            cv2.imwrite(save_path + str(i) + '_out.png', x)
            x2 = x2.astype('uint16')
            cv2.imwrite(save_path + str(i) + '_out2.png', x2)
            # cv2.imwrite(args.data+str(i)+'_out.png',x)
            # x2 = x2.astype('uint16')
            # cv2.imwrite(args.data+str(i)+'_out2.png',x2)
        
        depth_grad = get_gradient(depth)
        output_grad = get_gradient(output)
        depth_grad_dx = depth_grad[:, 0, :, :].contiguous().view_as(depth)
        depth_grad_dy = depth_grad[:, 1, :, :].contiguous().view_as(depth)
        output_grad_dx = output_grad[:, 0, :, :].contiguous().view_as(depth)
        output_grad_dy = output_grad[:, 1, :, :].contiguous().view_as(depth)
        depth_normal = torch.cat((-depth_grad_dx, -depth_grad_dy, ones), 1)
        output_normal = torch.cat((-output_grad_dx, -output_grad_dy, ones), 1)
        loss_depth = torch.log(torch.abs(output - depth) + 0.5).mean()
        loss_dx = torch.log(torch.abs(output_grad_dx - depth_grad_dx) + 0.5).mean()
        loss_dy = torch.log(torch.abs(output_grad_dy - depth_grad_dy) + 0.5).mean()
        loss_normal = torch.abs(1 - cos(output_normal, depth_normal)).mean()
        loss = loss_depth + loss_normal + (loss_dx + loss_dy)
        losses.update(loss.data, image.size(0))
        loss.backward()
        optimizer.step()
        batch_time.update(time.time() - end)
        end = time.time()
        batchSize = depth.size(0)

        print('Epoch: [{0}][{1}/{2}]\t'
          'Time {batch_time.val:.3f} ({batch_time.sum:.3f})\t'
          'Loss {loss.val:.4f} ({loss.avg:.4f})'
          .format(epoch, i, len(train_loader), batch_time=batch_time, loss=losses))
    log_value('training loss',losses.avg,epoch)

def adjust_learning_rate(optimizer, epoch): # 定义学习率
    lr = args.lr * (0.9 ** (epoch // 5))
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr

class AverageMeter(object):
    def __init__(self):
        self.reset()
    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0
    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count

def save_checkpoint(state, filename='test.pth.tar'):
    #旧的 torch.save(state, filename)
    torch.save(state, filename, _use_new_zipfile_serialization=True)
    return filename

if __name__ == '__main__':
    main()
